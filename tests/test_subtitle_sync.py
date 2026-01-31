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

    def test_sync_subtitles_actual_move_from_salvaged(self):
        """Sync from salvaged actually moves files into target/Subs."""
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
            (self.target_dir / "Movie1" / "Subs" / "subtitle.srt").read_text(),
            "content",
        )
        self.assertEqual(
            (
                self.target_dir / "Movie1" / "Subs" / "Subs" / "en.srt"
            ).read_text(),
            "en",
        )

    def test_sync_subtitles_actual_move_creates_subs_folder(self):
        """Sync creates Subs folder under target movie folder."""
        movie = self.salvaged_dir / "Some Movie"
        movie.mkdir()
        (movie / "sub.srt").write_text("sub")

        response = client.post(
            "/api/v1/sync/subtitles-to-target?source=salvaged&dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        subs_dir = self.target_dir / "Some Movie" / "Subs"
        self.assertTrue(subs_dir.is_dir())
        self.assertEqual((subs_dir / "sub.srt").read_text(), "sub")

    def test_sync_subtitles_skips_existing_file(self):
        """Sync skips files that already exist in target."""
        movie = self.salvaged_dir / "Movie1"
        movie.mkdir()
        (movie / "subtitle.srt").write_text("new")
        (movie / "other.srt").write_text("other")

        (self.target_dir / "Movie1" / "Subs").mkdir(parents=True)
        (self.target_dir / "Movie1" / "Subs" / "subtitle.srt").write_text(
            "existing"
        )

        response = client.post(
            "/api/v1/sync/subtitles-to-target?source=salvaged&dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["subtitle_files_moved"], 1)
        self.assertEqual(data["subtitle_files_skipped"], 1)
        self.assertEqual(
            (self.target_dir / "Movie1" / "Subs" / "subtitle.srt").read_text(),
            "existing",
        )
        self.assertEqual(
            (self.target_dir / "Movie1" / "Subs" / "other.srt").read_text(),
            "other",
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

        # Second request moves remaining 2
        response2 = client.post(
            "/api/v1/sync/subtitles-to-target?source=salvaged&dry_run=false"
            "&batch_size=10"
        )
        self.assertEqual(response2.status_code, 200)
        data2 = response2.json()
        self.assertEqual(data2["subtitle_files_moved"], 2)

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
