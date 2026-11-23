"""Artwork preparation, edge-tts chunk synthesis, FFmpeg broadcast mastering, and ID3 tagging."""

from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request

import edge_tts
from mutagen.id3 import APIC, ID3, TALB, TDRC, TIT2, TPE1, ID3NoHeaderError
from PIL import Image


def prepare_square_artwork(image_url: str, dest_path: Path, size: int = 1400) -> bool:
    """Download an image, center-crop to square, resize to size x size, and save RGB JPEG."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
    img_bytes = urllib.request.urlopen(req, timeout=25).read()

    with Image.open(BytesIO(img_bytes)) as img:
        if img.mode in ("RGBA", "LA", "P"):
            rgba = img.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.split()[3])
            rgb = background
        else:
            rgb = img.convert("RGB")

        width, height = rgb.size
        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2
        cropped = rgb.crop((left, top, left + side, top + side))
        resized = cropped.resize((size, size), Image.Resampling.LANCZOS)
        resized.save(dest_path, format="JPEG", quality=88, optimize=True)
    return True


async def _stream_edge_to_file(
    text: str,
    voice: str,
    rate: str,
    dest_path: Path,
    idle_timeout_sec: float,
    total_timeout_sec: float,
) -> None:
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    aiter = communicate.stream().__aiter__()
    deadline = time.monotonic() + total_timeout_sec
    try:
        with dest_path.open("wb") as fh:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"Total stream time exceeded {total_timeout_sec}s")
                try:
                    msg = await asyncio.wait_for(
                        aiter.__anext__(),
                        timeout=min(idle_timeout_sec, remaining),
                    )
                except StopAsyncIteration:
                    break
                if msg["type"] == "audio":
                    fh.write(msg["data"])
    finally:
        if hasattr(aiter, "aclose"):
            await aiter.aclose()


async def _synthesize_chunk_with_retry(
    text: str,
    voice: str,
    rate: str,
    dest_path: Path,
    attempts: int = 4,
    idle_timeout_sec: float = 25.0,
    total_timeout_sec: float = 180.0,
) -> None:
    last_err: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            dest_path.unlink(missing_ok=True)
            await _stream_edge_to_file(
                text,
                voice,
                rate,
                dest_path,
                idle_timeout_sec=idle_timeout_sec,
                total_timeout_sec=total_timeout_sec,
            )
            if dest_path.exists() and dest_path.stat().st_size > 0:
                return
            raise RuntimeError(f"Empty audio file generated for chunk {dest_path.name}")
        except Exception as exc:
            dest_path.unlink(missing_ok=True)
            last_err = exc
            if attempt < attempts:
                print(
                    f"    Retry {attempt}/{attempts - 1} for {dest_path.name} ({exc.__class__.__name__})...",
                    flush=True,
                )
                await asyncio.sleep(2 * attempt)
    raise RuntimeError(f"edge-tts failed after {attempts} attempts: {last_err}") from last_err


def _probe_mp3(mp3_path: Path) -> tuple[int, int]:
    """Return (duration_seconds_rounded, size_bytes) using ffprobe."""
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(mp3_path),
        ],
        text=True,
    ).strip()
    duration_sec = max(1, round(float(out)))
    return duration_sec, mp3_path.stat().st_size


def _embed_id3_tags(
    mp3_path: Path,
    title: str,
    artist: str,
    album: str,
    year: str,
    artwork_path: Path | None,
) -> None:
    try:
        tags = ID3(str(mp3_path))
    except ID3NoHeaderError:
        tags = ID3()

    tags.delall("TIT2")
    tags.delall("TPE1")
    tags.delall("TALB")
    tags.delall("TDRC")
    tags.delall("APIC")

    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=artist))
    tags.add(TALB(encoding=3, text=album))
    if year:
        tags.add(TDRC(encoding=3, text=year))
    if artwork_path and artwork_path.exists():
        tags.add(
            APIC(
                encoding=3,
                mime="image/jpeg",
                type=3,
                desc="Cover",
                data=artwork_path.read_bytes(),
            )
        )
    tags.save(str(mp3_path), v2_version=3)


async def _synthesize_all_chunks(
    body_chunks: list[str],
    outro_text: str | None,
    voice: str,
    rate: str,
    work_dir: Path,
) -> tuple[list[Path], Path | None]:
    sem = asyncio.Semaphore(4)
    total = len(body_chunks) + (1 if outro_text else 0)
    completed = 0

    async def _run_task(label: str, text: str, dest: Path) -> Path:
        nonlocal completed
        async with sem:
            await _synthesize_chunk_with_retry(text, voice, rate, dest)
            completed += 1
            print(f"    Synthesized {label} ({completed}/{total})", flush=True)
            return dest

    tasks = [
        _run_task(f"chunk {idx + 1}", chunk, work_dir / f"chunk_{idx:03d}.mp3")
        for idx, chunk in enumerate(body_chunks)
    ]
    outro_task = None
    if outro_text:
        outro_task = _run_task("outro", outro_text, work_dir / "outro.mp3")
        tasks.append(outro_task)

    results = await asyncio.gather(*tasks)
    if outro_task is not None:
        return list(results[:-1]), results[-1]
    return list(results), None


def synthesize_and_master_mp3(
    body_chunks: list[str],
    outro_text: str | None,
    output_mp3: Path,
    voice: str,
    rate: str,
    title: str,
    artist: str,
    album: str,
    year: str,
    artwork_path: Path | None,
    bitrate: str = "64k",
    sample_rate: int = 44100,
) -> tuple[int, int]:
    """Synthesize spoken chunks, insert natural pauses, apply broadcast mastering, and embed ID3."""
    output_mp3.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        work_dir = Path(tmp_dir_str)
        chunk_paths, outro_path = asyncio.run(
            _synthesize_all_chunks(body_chunks, outro_text, voice, rate, work_dir)
        )

        # Build silent pause segments at target sample rate
        pause_between = work_dir / "pause_400ms.wav"
        pause_outro = work_dir / "pause_700ms.wav"
        for dur, dest in ((0.4, pause_between), (0.7, pause_outro)):
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    f"anullsrc=r={sample_rate}:cl=mono",
                    "-t",
                    str(dur),
                    str(dest),
                ],
                check=True,
            )

        # Assemble ordered list of audio segments (leading & trailing silence included directly)
        segments: list[Path] = [pause_between]
        for idx, cp in enumerate(chunk_paths):
            segments.append(cp)
            if idx < len(chunk_paths) - 1:
                segments.append(pause_between)
        if outro_path is not None:
            segments.append(pause_outro)
            segments.append(outro_path)
        segments.append(pause_outro)

        # Use filter_complex concat so MP3 chunk boundaries never click or drift
        cmd: list[str] = ["ffmpeg", "-y", "-loglevel", "error"]
        for seg in segments:
            cmd.extend(["-i", str(seg)])

        norm_streams = "".join(
            f"[{i}:a]aresample={sample_rate},aformat=sample_fmts=fltp:channel_layouts=mono[a{i}];"
            for i in range(len(segments))
        )
        concat_inputs = "".join(f"[a{i}]" for i in range(len(segments)))
        master_chain = (
            "highpass=f=75,"
            "equalizer=f=180:t=q:w=1.2:g=1.8,"
            "equalizer=f=3200:t=q:w=1.5:g=1.2,"
            "acompressor=threshold=-20dB:ratio=2.2:attack=15:release=180:makeup=1dB,"
            "loudnorm=I=-16:TP=-1.5:LRA=11,"
            "asetpts=N/SR/TB"
        )
        filter_complex = (
            f"{norm_streams}"
            f"{concat_inputs}concat=n={len(segments)}:v=0:a=1[joined];"
            f"[joined]{master_chain}[out]"
        )

        cmd.extend(
            [
                "-filter_complex",
                filter_complex,
                "-map",
                "[out]",
                "-codec:a",
                "libmp3lame",
                "-b:a",
                bitrate,
                "-ar",
                str(sample_rate),
                "-ac",
                "1",
                str(output_mp3),
            ]
        )
        subprocess.run(cmd, check=True)

    _embed_id3_tags(output_mp3, title, artist, album, year, artwork_path)
    return _probe_mp3(output_mp3)
