"""Unit tests for deterministic backfill sharding, pipeline versioning, and shard merging."""

import json
from pathlib import Path
import tempfile
import unittest

from src.sync_podcast import PIPELINE_VERSION, merge_shard_outputs, select_pending_posts


ROOT_DIR = Path(__file__).resolve().parent.parent


class TestBackfillSharding(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        queue_path = ROOT_DIR / "state" / "backfill_queue.json"
        cls.backfill_posts = json.loads(queue_path.read_text(encoding="utf-8"))["posts"]

    def test_six_way_shard_partition_covers_all_51_posts_evenly(self) -> None:
        all_slugs = {p["slug"] for p in self.backfill_posts}
        self.assertGreaterEqual(len(all_slugs), 51)

        # Simulate existing v1 episodes (mixed missing & pipeline_version=1)
        episodes = {
            p["slug"]: {"slug": p["slug"], "pipeline_version": 1}
            for p in self.backfill_posts[:40]
        }

        seen: list[str] = []
        counts: list[int] = []
        for idx in range(6):
            shard_posts = select_pending_posts(
                all_posts=self.backfill_posts,
                episodes=episodes,
                ignored_slugs=set(),
                order="oldest",
                upgrade_outdated=True,
                shard_index=idx,
                shard_count=6,
            )
            counts.append(len(shard_posts))
            seen.extend(p["slug"] for p in shard_posts)

        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(set(seen), all_slugs)
        self.assertTrue(all(8 <= c <= 9 for c in counts), f"Imbalanced shard counts: {counts}")

    def test_upgrade_outdated_skips_v2_and_non_upgrade_skips_existing(self) -> None:
        posts = [
            {"slug": "old-v1", "post_date": "2025-01-01T00:00:00Z"},
            {"slug": "missing-ver", "post_date": "2025-01-02T00:00:00Z"},
            {"slug": "new-v2", "post_date": "2025-01-03T00:00:00Z"},
            {"slug": "brand-new", "post_date": "2025-01-04T00:00:00Z"},
        ]
        episodes = {
            "old-v1": {"slug": "old-v1", "pipeline_version": 1},
            "missing-ver": {"slug": "missing-ver"},
            "new-v2": {"slug": "new-v2", "pipeline_version": PIPELINE_VERSION},
        }

        normal = select_pending_posts(posts, episodes, ignored_slugs=set(), upgrade_outdated=False)
        self.assertEqual([p["slug"] for p in normal], ["brand-new"])

        upgraded = select_pending_posts(posts, episodes, ignored_slugs=set(), upgrade_outdated=True)
        self.assertEqual([p["slug"] for p in upgraded], ["old-v1", "missing-ver", "brand-new"])

    def test_merge_shard_outputs_prefers_v2_and_copies_artwork(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_file = root / "state" / "episodes.json"
            state_file.parent.mkdir(parents=True, exist_ok=True)
            state_file.write_text(
                json.dumps(
                    {
                        "episodes": {
                            "ep-1": {"slug": "ep-1", "title": "Old", "pipeline_version": 1, "generated_at": "2026-01-01T00:00:00Z"},
                            "ep-keep": {"slug": "ep-keep", "title": "Keep", "pipeline_version": 2, "generated_at": "2026-01-02T00:00:00Z"},
                        }
                    }
                ),
                encoding="utf-8",
            )

            shards_dir = root / "shards"
            s0 = shards_dir / "podcast-shard-0"
            s1 = shards_dir / "podcast-shard-1"
            (s0 / "artwork").mkdir(parents=True)
            (s1 / "artwork").mkdir(parents=True)

            (s0 / "episodes.json").write_text(
                json.dumps(
                    {
                        "episodes": {
                            "ep-1": {"slug": "ep-1", "title": "Upgraded", "pipeline_version": 2, "generated_at": "2026-01-03T00:00:00Z"},
                        }
                    }
                ),
                encoding="utf-8",
            )
            (s1 / "episodes.json").write_text(
                json.dumps(
                    {
                        "episodes": {
                            "ep-2": {"slug": "ep-2", "title": "Second", "pipeline_version": 2, "generated_at": "2026-01-03T00:00:00Z"},
                        }
                    }
                ),
                encoding="utf-8",
            )
            (s0 / "artwork" / "ep-1.jpg").write_bytes(b"jpg-1")
            (s1 / "artwork" / "ep-2.jpg").write_bytes(b"jpg-2")

            artwork_dir = root / "docs" / "artwork"
            merged, count = merge_shard_outputs(shards_dir, state_file, artwork_dir)
            self.assertEqual(count, 2)
            eps = merged["episodes"]
            self.assertEqual(set(eps.keys()), {"ep-1", "ep-2", "ep-keep"})
            self.assertEqual(eps["ep-1"]["title"], "Upgraded")
            self.assertEqual(eps["ep-1"]["pipeline_version"], 2)
            self.assertEqual((artwork_dir / "ep-1.jpg").read_bytes(), b"jpg-1")
            self.assertEqual((artwork_dir / "ep-2.jpg").read_bytes(), b"jpg-2")
