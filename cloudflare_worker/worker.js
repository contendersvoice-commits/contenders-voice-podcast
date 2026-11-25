const UPSTREAM_BASE =
  "https://github.com/contendersvoice-commits/contenders-voice-podcast/releases/download/audio-archive/";

export default {
  async fetch(request) {
    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
          "Access-Control-Allow-Headers": "Range, If-None-Match, If-Modified-Since",
          "Access-Control-Max-Age": "86400",
        },
      });
    }

    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const url = new URL(request.url);
    const filename = url.pathname.replace(/^\/+/, "");
    if (!filename || !/^[a-zA-Z0-9._-]+\.mp3$/.test(filename)) {
      return new Response("Not Found", { status: 404 });
    }

    const upstreamHeaders = new Headers({
      "User-Agent": "ContendersVoiceAudioProxy/1.0",
    });
    const range = request.headers.get("Range");
    if (range) upstreamHeaders.set("Range", range);

    const upstreamResp = await fetch(UPSTREAM_BASE + filename, {
      method: request.method,
      headers: upstreamHeaders,
      redirect: "follow",
    });

    if (!upstreamResp.ok && upstreamResp.status !== 206) {
      return new Response("Audio not found", { status: upstreamResp.status });
    }

    const headers = new Headers();
    headers.set("Content-Type", "audio/mpeg");
    headers.set("Accept-Ranges", "bytes");
    headers.set("Access-Control-Allow-Origin", "*");
    headers.set(
      "Access-Control-Expose-Headers",
      "Content-Length, Content-Range, Accept-Ranges",
    );
    headers.set("Cache-Control", "public, max-age=86400");

    for (const key of ["Content-Length", "Content-Range", "ETag", "Last-Modified"]) {
      const val = upstreamResp.headers.get(key);
      if (val) headers.set(key, val);
    }

    return new Response(request.method === "HEAD" ? null : upstreamResp.body, {
      status: upstreamResp.status,
      headers,
    });
  },
};
