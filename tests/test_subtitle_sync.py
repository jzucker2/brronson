"""Tests for subtitle sync to target endpoint."""

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestSubtitleSync(unittest.TestCase):
    """Test the subtitle sync to target functionality."""

    def setUp(self):
        """Set up test directories for subtitle sync."""
        self.test_dir = tempfile.mkdtemp()
        self.salvaged_dir = Path(self.test_dir) / "salvaged"
        self.migrated_dir = Path(self.test_dir) / "migrated"
        self.target_dir = Path(self.test_dir) / "target"

        self.salvaged_dir.mkdir()
        self.migrated_dir.mkdir()
        self.target_dir.mkdir()

        self.original_salvaged = os.environ.get("SALVAGED_MOVIES_DIRECTORY")
        self.original_migrated = os.environ.get("MIGRATED_MOVIES_DIRECTORY")
        self.original_target = os.environ.get("TARGET_DIRECTORY")

        os.environ["SALVAGED_MOVIES_DIRECTORY"] = str(self.salvaged_dir)
        os.environ["MIGRATED_MOVIES_DIRECTORY"] = str(self.migrated_dir)
        os.environ["TARGET_DIRECTORY"] = str(self.target_dir)

        import prometheus_client

        prometheus_client.REGISTRY._names_to_collectors.clear()
        from importlib import reload

        import app.main

        reload(app.main)
        global client
        client = TestClient(app.main.app)

    def tearDown(self):
        """Clean up test directories and restore environment."""
        import shutil

        shutil.rmtree(self.test_dir, ignore_errors=True)
        for name, orig in [
            ("SALVAGED_MOVIES_DIRECTORY", self.original_salvaged),
            ("MIGRATED_MOVIES_DIRECTORY", self.original_migrated),
            ("TARGET_DIRECTORY", self.original_target),
        ]:
            if orig is not None:
                os.environ[name] = orig
            elif name in os.environ:
                del os.environ[name]

    def test_sync_subtitles_missing_source_param(self):
        """Sync requires source query param."""
        response = client.post("/api/v1/sync/subtitles-to-target")
        self.assertEqual(response.status_code, 422)

    def test_sync_subtitles_invalid_source(self):
        """Sync rejects invalid source value."""
        response = client.post(
            "/api/v1/sync/subtitles-to-target?source=invalid"
        )
        self.assertEqual(response.status_code, 422)

    def test_sync_subtitles_from_salvaged_dry_run(self):
        """Sync from salvaged in dry run reports what would be moved."""
        movie = self.salvaged_dir / "Movie1"
        movie.mkdir()
        (movie / "subtitle.srt").touch()
        (movie / "Subs").mkdir()
        (movie / "Subs" / "en.srt").touch()

        response = client.post(
            "/api/v1/sync/subtitles-to-target?source=salvaged"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["source"], "salvaged")
        self.assertTrue(data["dry_run"])
        self.assertEqual(data["subtitle_files_moved"], 2)
        self.assertEqual(data["subtitle_files_skipped"], 0)
        self.assertTrue((movie / "subtitle.srt").exists())
        self.assertTrue((movie / "Subs" / "en.srt").exists())

    def test_sync_subtitles_from_migrated_dry_run(self):
        """Sync from migrated in dry run reports what would be moved."""
        movie = self.migrated_dir / "Movie2"
        movie.mkdir()
        (movie / "sub.srt").touch()

        response = client.post(
            "/api/v1/sync/subtitles-to-target?source=migrated"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["source"], "migrated")
        self.assertEqual(data["subtitle_files_moved"], 1)
        self.assertTrue((movie / "sub.srt").exists())

    def test_sync_preserves_hierarchy_root_and_subs(self):
        """Files go to equivalent path: root stays root, Subs/ stays Subs/."""
        movie = self.salvaged_dir / "Movie1"
        movie.mkdir()
        (movie / "subtitle.srt").write_text("content")
        (movie / "Subs").mkdir()
        (movie / "Subs" / "en.srt").write_text("en")

        response = client.post(
            "/api/v1/sync/subtitles-to-target?source=salvaged&dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["subtitle_files_moved"], 2)
        self.assertEqual(data["subtitle_files_skipped"], 0)

        self.assertFalse((movie / "subtitle.srt").exists())
        self.assertFalse((movie / "Subs" / "en.srt").exists())
        self.assertEqual(
            (self.target_dir / "Movie1" / "subtitle.srt").read_text(),
            "content",
        )
        self.assertEqual(
            (self.target_dir / "Movie1" / "Subs" / "en.srt").read_text(),
            "en",
        )

    def test_sync_root_only_subtitle_equivalent_path(self):
        """Subtitle in source movie root goes to target movie root."""
        movie = self.salvaged_dir / "Some Movie"
        movie.mkdir()
        (movie / "sub.srt").write_text("sub")

        response = client.post(
            "/api/v1/sync/subtitles-to-target?source=salvaged&dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            (self.target_dir / "Some Movie" / "sub.srt").read_text(), "sub"
        )

    def test_sync_subtitle_in_source_subs_equivalent_path(self):
        """Subtitle in source/Subs goes to target/Subs (same path)."""
        movie = self.salvaged_dir / "MovieB"
        movie.mkdir()
        (movie / "Subs").mkdir()
        (movie / "Subs" / "en.srt").write_text("en")
        response = client.post(
            "/api/v1/sync/subtitles-to-target?source=salvaged&dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            (self.target_dir / "MovieB" / "Subs" / "en.srt").read_text(),
            "en",
        )

    def test_sync_all_match_none_copied(self):
        """When every source file already exists in target, all skipped."""
        movie = self.salvaged_dir / "Movie1"
        movie.mkdir()
        (movie / "a.srt").write_text("a")
        (movie / "Subs").mkdir()
        (movie / "Subs" / "b.srt").write_text("b")

        (self.target_dir / "Movie1").mkdir()
        (self.target_dir / "Movie1" / "a.srt").write_text("a")
        (self.target_dir / "Movie1" / "Subs").mkdir()
        (self.target_dir / "Movie1" / "Subs" / "b.srt").write_text("b")

        response = client.post(
            "/api/v1/sync/subtitles-to-target?source=salvaged&dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["subtitle_files_moved"], 0)
        self.assertEqual(data["subtitle_files_skipped"], 2)
        self.assertTrue((movie / "a.srt").exists())
        self.assertTrue((movie / "Subs" / "b.srt").exists())

    def test_sync_none_in_target_all_copied(self):
        """When nothing exists in target, all subtitle files are moved."""
        movie = self.salvaged_dir / "Movie1"
        movie.mkdir()
        (movie / "one.srt").write_text("1")
        (movie / "Subs").mkdir()
        (movie / "Subs" / "two.srt").write_text("2")

        response = client.post(
            "/api/v1/sync/subtitles-to-target?source=salvaged&dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["subtitle_files_moved"], 2)
        self.assertEqual(data["subtitle_files_skipped"], 0)
        self.assertEqual(
            (self.target_dir / "Movie1" / "one.srt").read_text(), "1"
        )
        self.assertEqual(
            (self.target_dir / "Movie1" / "Subs" / "two.srt").read_text(), "2"
        )

    def test_sync_some_match_some_copied(self):
        """When some files exist in target, only missing ones are moved."""
        movie = self.salvaged_dir / "Movie1"
        movie.mkdir()
        (movie / "existing.srt").write_text("new")
        (movie / "missing.srt").write_text("missing")
        (movie / "Subs").mkdir()
        (movie / "Subs" / "also_missing.srt").write_text("also")

        (self.target_dir / "Movie1").mkdir()
        (self.target_dir / "Movie1" / "existing.srt").write_text("keep")

        response = client.post(
            "/api/v1/sync/subtitles-to-target?source=salvaged&dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["subtitle_files_moved"], 2)
        self.assertEqual(data["subtitle_files_skipped"], 1)
        self.assertEqual(
            (self.target_dir / "Movie1" / "existing.srt").read_text(), "keep"
        )
        self.assertEqual(
            (self.target_dir / "Movie1" / "missing.srt").read_text(),
            "missing",
        )
        self.assertEqual(
            (
                self.target_dir / "Movie1" / "Subs" / "also_missing.srt"
            ).read_text(),
            "also",
        )

    def test_sync_subtitles_skips_existing_file(self):
        """Sync skips files that already exist in target (single file)."""
        movie = self.salvaged_dir / "Movie1"
        movie.mkdir()
        (movie / "subtitle.srt").write_text("new")
        (movie / "other.srt").write_text("other")

        (self.target_dir / "Movie1").mkdir()
        (self.target_dir / "Movie1" / "subtitle.srt").write_text("existing")

        response = client.post(
            "/api/v1/sync/subtitles-to-target?source=salvaged&dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["subtitle_files_moved"], 1)
        self.assertEqual(data["subtitle_files_skipped"], 1)
        self.assertEqual(
            (self.target_dir / "Movie1" / "subtitle.srt").read_text(),
            "existing",
        )
        self.assertEqual(
            (self.target_dir / "Movie1" / "other.srt").read_text(), "other"
        )

    def test_sync_subtitles_batch_size(self):
        """batch_size limits number of files moved per request."""
        movie = self.salvaged_dir / "Movie1"
        movie.mkdir()
        for i in range(5):
            (movie / f"sub{i}.srt").touch()

        response = client.post(
            "/api/v1/sync/subtitles-to-target?source=salvaged&dry_run=false"
            "&batch_size=3"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["batch_size"], 3)
        self.assertEqual(data["subtitle_files_moved"], 3)
        self.assertTrue(data["batch_limit_reached"])

        response2 = client.post(
            "/api/v1/sync/subtitles-to-target?source=salvaged&dry_run=false"
            "&batch_size=10"
        )
        self.assertEqual(response2.status_code, 200)
        data2 = response2.json()
        self.assertEqual(data2["subtitle_files_moved"], 2)

    def test_sync_collects_files_in_deterministic_order(self):
        """Files are processed in sorted path order for re-entrant batch_size."""
        movie = self.salvaged_dir / "Movie1"
        movie.mkdir()
        (movie / "root.srt").write_text("root")
        (movie / "Subs").mkdir()
        (movie / "Subs" / "a.srt").write_text("a")
        (movie / "Subs" / "z.srt").write_text("z")
        # Path sort order: .../Subs/a.srt, .../Subs/z.srt, .../root.srt
        response = client.post(
            "/api/v1/sync/subtitles-to-target?source=salvaged&dry_run=false"
            "&batch_size=2"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["subtitle_files_moved"], 2)
        self.assertTrue(data["batch_limit_reached"])
        # First two by path order: Subs/a.srt, Subs/z.srt
        self.assertFalse((movie / "Subs" / "a.srt").exists())
        self.assertFalse((movie / "Subs" / "z.srt").exists())
        self.assertTrue((movie / "root.srt").exists())
        self.assertEqual(
            (self.target_dir / "Movie1" / "Subs" / "a.srt").read_text(), "a"
        )
        self.assertEqual(
            (self.target_dir / "Movie1" / "Subs" / "z.srt").read_text(), "z"
        )
        response2 = client.post(
            "/api/v1/sync/subtitles-to-target?source=salvaged&dry_run=false"
            "&batch_size=10"
        )
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(response2.json()["subtitle_files_moved"], 1)
        self.assertEqual(
            (self.target_dir / "Movie1" / "root.srt").read_text(), "root"
        )

    def test_sync_creates_target_directory_when_missing(self):
        """Target directory is created when it does not exist (salvage pattern)."""
        target_missing = Path(self.test_dir) / "target_missing"
        self.assertFalse(target_missing.exists())
        os.environ["TARGET_DIRECTORY"] = str(target_missing)
        from importlib import reload
        import app.main

        reload(app.main)
        global client
        client = TestClient(app.main.app)

        movie = self.salvaged_dir / "Movie1"
        movie.mkdir()
        (movie / "sub.srt").write_text("sub")

        response = client.post(
            "/api/v1/sync/subtitles-to-target?source=salvaged&dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(target_missing.is_dir())
        self.assertEqual(
            (target_missing / "Movie1" / "sub.srt").read_text(), "sub"
        )

    def test_sync_subtitles_batch_size_validation(self):
        """batch_size must be positive."""
        response = client.post(
            "/api/v1/sync/subtitles-to-target?source=salvaged&batch_size=0"
        )
        self.assertEqual(response.status_code, 400)
        response = client.post(
            "/api/v1/sync/subtitles-to-target?source=salvaged&batch_size=-1"
        )
        self.assertEqual(response.status_code, 400)

    def test_sync_subtitles_nonexistent_source(self):
        """Sync returns 404 when source directory does not exist."""
        os.environ["SALVAGED_MOVIES_DIRECTORY"] = str(
            self.test_dir + "/nonexistent"
        )
        from importlib import reload

        import app.main

        reload(app.main)
        global client
        client = TestClient(app.main.app)

        response = client.post(
            "/api/v1/sync/subtitles-to-target?source=salvaged"
        )
        self.assertEqual(response.status_code, 404)
