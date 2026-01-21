import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from tests.test_utils import (
    assert_metric_with_labels,
    normalize_path_for_metrics,
)

client = TestClient(app)


class TestSubtitleRecovery(unittest.TestCase):
    """Test the subtitle recovery functionality"""

    def setUp(self):
        """Set up test directories for subtitle recovery"""
        self.test_dir = tempfile.mkdtemp()
        self.recycled_dir = Path(self.test_dir) / "recycled"
        self.recovered_dir = Path(self.test_dir) / "recovered"

        # Create test directories
        self.recycled_dir.mkdir()
        self.recovered_dir.mkdir()

        # Set environment variables
        self.original_recycled_dir = os.environ.get(
            "RECYCLED_MOVIES_DIRECTORY"
        )
        self.original_recovered_dir = os.environ.get(
            "RECOVERED_MOVIES_DIRECTORY"
        )
        os.environ["RECYCLED_MOVIES_DIRECTORY"] = str(self.recycled_dir)
        os.environ["RECOVERED_MOVIES_DIRECTORY"] = str(self.recovered_dir)

        # Clear Prometheus default registry
        import prometheus_client

        prometheus_client.REGISTRY._names_to_collectors.clear()

        # Re-import and re-create the TestClient
        from importlib import reload

        import app.main

        reload(app.main)
        global client
        client = TestClient(app.main.app)

    def tearDown(self):
        """Clean up test directories and restore environment"""
        import shutil

        shutil.rmtree(self.test_dir, ignore_errors=True)

        if self.original_recycled_dir is not None:
            os.environ["RECYCLED_MOVIES_DIRECTORY"] = (
                self.original_recycled_dir
            )
        elif "RECYCLED_MOVIES_DIRECTORY" in os.environ:
            del os.environ["RECYCLED_MOVIES_DIRECTORY"]

        if self.original_recovered_dir is not None:
            os.environ["RECOVERED_MOVIES_DIRECTORY"] = (
                self.original_recovered_dir
            )
        elif "RECOVERED_MOVIES_DIRECTORY" in os.environ:
            del os.environ["RECOVERED_MOVIES_DIRECTORY"]

    def test_recover_subtitle_folders_dry_run(self):
        """Test subtitle recovery endpoint in dry run mode (default)"""
        # Create folder with subtitle in root
        folder_with_subtitle = self.recycled_dir / "Movie1"
        folder_with_subtitle.mkdir()
        (folder_with_subtitle / "movie.mp4").touch()  # Media file
        (folder_with_subtitle / "subtitle.srt").touch()  # Subtitle file
        (folder_with_subtitle / "poster.jpg").touch()  # Image file

        # Create folder without subtitle in root
        folder_without_subtitle = self.recycled_dir / "Movie2"
        folder_without_subtitle.mkdir()
        (folder_without_subtitle / "movie.mp4").touch()
        (folder_without_subtitle / "subdir").mkdir()
        (folder_without_subtitle / "subdir" / "subtitle.srt").touch()

        response = client.post("/api/v1/recover/subtitle-folders")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check response structure
        self.assertIn("recycled_directory", data)
        self.assertIn("recovered_directory", data)
        self.assertIn("dry_run", data)
        self.assertIn("subtitle_extensions", data)
        self.assertIn("folders_scanned", data)
        self.assertIn("folders_with_subtitles_found", data)
        self.assertIn("folders_copied", data)
        self.assertIn("subtitle_files_copied", data)
        self.assertIn("errors", data)
        self.assertIn("folders_with_subtitles", data)
        self.assertIn("copied_folders", data)
        self.assertIn("error_details", data)

        # Check expected results (dry run)
        self.assertTrue(data["dry_run"])
        self.assertEqual(data["folders_scanned"], 2)
        self.assertEqual(
            data["folders_with_subtitles_found"], 1
        )  # Only Movie1
        self.assertEqual(data["folders_copied"], 1)
        self.assertEqual(data["folders_skipped"], 0)
        self.assertEqual(data["subtitle_files_copied"], 1)  # Only subtitle.srt
        self.assertEqual(data["subtitle_files_skipped"], 0)
        self.assertEqual(data["errors"], 0)

        # Verify files still exist in original location (dry run)
        self.assertTrue((folder_with_subtitle / "movie.mp4").exists())
        self.assertTrue((folder_with_subtitle / "subtitle.srt").exists())
        self.assertTrue((folder_with_subtitle / "poster.jpg").exists())

    def test_recover_subtitle_folders_actual_move(self):
        """Test subtitle recovery endpoint with actual folder copying"""
        # Create folder with subtitle in root
        folder_with_subtitle = self.recycled_dir / "Movie1"
        folder_with_subtitle.mkdir()
        (
            folder_with_subtitle / "movie.mp4"
        ).touch()  # Media file - should not move
        (
            folder_with_subtitle / "subtitle.srt"
        ).touch()  # Subtitle file - should move
        (
            folder_with_subtitle / "poster.jpg"
        ).touch()  # Image file - should not copy
        (
            folder_with_subtitle / "info.nfo"
        ).touch()  # Other file - should not copy

        # Create subdirectory with subtitle
        (folder_with_subtitle / "subs").mkdir()
        (
            folder_with_subtitle / "subs" / "subtitle2.srt"
        ).touch()  # Should move

        response = client.post(
            "/api/v1/recover/subtitle-folders?dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check expected results
        self.assertFalse(data["dry_run"])
        self.assertEqual(data["folders_with_subtitles_found"], 1)
        self.assertEqual(data["folders_copied"], 1)
        self.assertEqual(data["folders_skipped"], 0)
        self.assertEqual(
            data["subtitle_files_copied"], 2
        )  # subtitle.srt and subtitle2.srt
        self.assertEqual(data["subtitle_files_skipped"], 0)
        self.assertEqual(data["errors"], 0)

        # Verify folder was copied to recovered directory
        self.assertTrue((self.recovered_dir / "Movie1").exists())
        self.assertTrue(
            (self.recovered_dir / "Movie1" / "subtitle.srt").exists()
        )
        self.assertTrue(
            (self.recovered_dir / "Movie1" / "subs" / "subtitle2.srt").exists()
        )
        # Verify non-subtitle files are NOT copied
        self.assertFalse((self.recovered_dir / "Movie1" / "info.nfo").exists())

        # Verify media files were NOT copied (should not be in recovered)
        self.assertFalse(
            (self.recovered_dir / "Movie1" / "movie.mp4").exists()
        )
        self.assertFalse(
            (self.recovered_dir / "Movie1" / "poster.jpg").exists()
        )

        # Verify original files still exist in recycled directory (copied, not moved)
        self.assertTrue((self.recycled_dir / "Movie1" / "movie.mp4").exists())
        self.assertTrue((self.recycled_dir / "Movie1" / "poster.jpg").exists())
        self.assertTrue(
            (self.recycled_dir / "Movie1" / "subtitle.srt").exists()
        )
        self.assertTrue(
            (self.recycled_dir / "Movie1" / "subs" / "subtitle2.srt").exists()
        )
        self.assertTrue((self.recycled_dir / "Movie1" / "info.nfo").exists())

        # Verify original folder still exists (files were copied, not moved)
        self.assertTrue((self.recycled_dir / "Movie1").exists())

    def test_recover_subtitle_folders_multiple_subtitle_formats(self):
        """Test subtitle recovery with multiple subtitle file formats"""
        folder = self.recycled_dir / "Movie1"
        folder.mkdir()
        (folder / "subtitle.srt").touch()
        (folder / "subtitle.ass").touch()
        (folder / "subtitle.vtt").touch()
        (folder / "subtitle.sub").touch()

        response = client.post(
            "/api/v1/recover/subtitle-folders?dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["subtitle_files_copied"], 4)
        self.assertTrue(
            (self.recovered_dir / "Movie1" / "subtitle.srt").exists()
        )
        self.assertTrue(
            (self.recovered_dir / "Movie1" / "subtitle.ass").exists()
        )
        self.assertTrue(
            (self.recovered_dir / "Movie1" / "subtitle.vtt").exists()
        )
        self.assertTrue(
            (self.recovered_dir / "Movie1" / "subtitle.sub").exists()
        )

    def test_recover_subtitle_folders_custom_extensions(self):
        """Test subtitle recovery with custom subtitle extensions"""
        folder = self.recycled_dir / "Movie1"
        folder.mkdir()
        (folder / "subtitle.srt").touch()
        (folder / "subtitle.custom").touch()  # Custom extension

        custom_extensions = [".srt", ".custom"]

        response = client.post(
            "/api/v1/recover/subtitle-folders?dry_run=false",
            json=custom_extensions,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check that custom extensions were used
        self.assertIn(".srt", data["subtitle_extensions"])
        self.assertIn(".custom", data["subtitle_extensions"])
        # Should have copied both files
        self.assertEqual(data["subtitle_files_copied"], 2)

    def test_recover_subtitle_folders_no_subtitles(self):
        """Test subtitle recovery when no folders have subtitles"""
        # Create folder without subtitle in root
        folder = self.recycled_dir / "Movie1"
        folder.mkdir()
        (folder / "movie.mp4").touch()
        (folder / "poster.jpg").touch()

        response = client.post("/api/v1/recover/subtitle-folders")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["folders_scanned"], 1)
        self.assertEqual(data["folders_with_subtitles_found"], 0)
        self.assertEqual(data["folders_copied"], 0)
        self.assertEqual(data["subtitle_files_copied"], 0)

    def test_recover_subtitle_folders_empty_directories(self):
        """Test subtitle recovery with empty directories"""
        response = client.post("/api/v1/recover/subtitle-folders")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["folders_scanned"], 0)
        self.assertEqual(data["folders_with_subtitles_found"], 0)
        self.assertEqual(data["folders_copied"], 0)

    def test_recover_subtitle_folders_nonexistent_recycled(self):
        """Test subtitle recovery with nonexistent recycled directory"""
        os.environ["RECYCLED_MOVIES_DIRECTORY"] = "/nonexistent/recycled"

        response = client.post("/api/v1/recover/subtitle-folders")
        self.assertEqual(response.status_code, 404)

    def test_recover_subtitle_folders_nonexistent_recovered(self):
        """Test subtitle recovery with nonexistent recovered directory"""
        # Create recycled directory with content
        folder = self.recycled_dir / "Movie1"
        folder.mkdir()
        (folder / "subtitle.srt").touch()

        os.environ["RECOVERED_MOVIES_DIRECTORY"] = "/nonexistent/recovered"

        response = client.post("/api/v1/recover/subtitle-folders")
        self.assertEqual(response.status_code, 404)

    def test_recover_subtitle_folders_metrics(self):
        """Test that subtitle recovery records metrics"""
        # Create folder with subtitle
        folder = self.recycled_dir / "Movie1"
        folder.mkdir()
        (folder / "subtitle.srt").touch()

        response = client.post("/api/v1/recover/subtitle-folders")
        self.assertEqual(response.status_code, 200)

        # Check metrics
        metrics_response = client.get("/metrics")
        metrics_text = metrics_response.text

        # Should have recovery metrics
        self.assertIn("brronson_recovery_folders_scanned_total", metrics_text)
        self.assertIn(
            "brronson_recovery_folders_with_subtitles_found", metrics_text
        )
        self.assertIn(
            "brronson_recovery_operation_duration_seconds", metrics_text
        )

        # Use the resolved path format
        recycled_path_resolved = normalize_path_for_metrics(self.recycled_dir)

        # Check folders scanned metric
        assert_metric_with_labels(
            metrics_text,
            "brronson_recovery_folders_scanned_total",
            {
                "recycled_directory": recycled_path_resolved,
                "dry_run": "true",
            },
            "1.0",
        )

        # Check folders with subtitles found metric
        assert_metric_with_labels(
            metrics_text,
            "brronson_recovery_folders_with_subtitles_found",
            {
                "recycled_directory": recycled_path_resolved,
                "dry_run": "true",
            },
            "1.0",
        )

    def test_recover_subtitle_folders_target_exists(self):
        """Test subtitle recovery when target folder already exists"""
        # Create folder with subtitle in recycled
        folder = self.recycled_dir / "Movie1"
        folder.mkdir()
        (folder / "subtitle.srt").touch()

        # Create folder with same name in recovered (empty folder)
        (self.recovered_dir / "Movie1").mkdir()

        response = client.post(
            "/api/v1/recover/subtitle-folders?dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Should copy files into existing folder, not skip
        self.assertEqual(data["errors"], 0)
        self.assertEqual(data["folders_copied"], 1)
        self.assertEqual(data["folders_skipped"], 0)
        self.assertIn("Movie1", data["copied_folders"])
        self.assertEqual(data["subtitle_files_copied"], 1)
        self.assertEqual(data["subtitle_files_skipped"], 0)

        # Verify file was copied into existing folder
        self.assertTrue(
            (self.recovered_dir / "Movie1" / "subtitle.srt").exists()
        )

    def test_recover_subtitle_folders_file_exists(self):
        """Test subtitle recovery when destination file already exists"""
        # Create folder with subtitle in recycled
        folder = self.recycled_dir / "Movie1"
        folder.mkdir()
        (folder / "subtitle.srt").touch()
        (folder / "subtitle2.srt").touch()

        # Create folder and one subtitle file in recovered
        (self.recovered_dir / "Movie1").mkdir()
        (self.recovered_dir / "Movie1" / "subtitle.srt").write_text("existing")

        response = client.post(
            "/api/v1/recover/subtitle-folders?dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Should copy folder but skip existing file
        self.assertEqual(data["folders_copied"], 1)
        self.assertEqual(
            data["subtitle_files_copied"], 1
        )  # Only subtitle2.srt
        self.assertEqual(
            data["subtitle_files_skipped"], 1
        )  # subtitle.srt skipped

        # Verify existing file was not overwritten
        self.assertEqual(
            (self.recovered_dir / "Movie1" / "subtitle.srt").read_text(),
            "existing",
        )
        # Verify new file was copied
        self.assertTrue(
            (self.recovered_dir / "Movie1" / "subtitle2.srt").exists()
        )

    def test_recover_subtitle_folders_dry_run_skips_existing(self):
        """Test that dry run correctly identifies folders/files that would be skipped"""
        # Create folder with subtitle in recycled
        folder = self.recycled_dir / "Movie1"
        folder.mkdir()
        (folder / "subtitle.srt").touch()

        # Create folder and file in recovered
        (self.recovered_dir / "Movie1").mkdir()
        (self.recovered_dir / "Movie1" / "subtitle.srt").touch()

        response = client.post("/api/v1/recover/subtitle-folders")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Dry run should show skip
        self.assertTrue(data["dry_run"])
        self.assertEqual(data["folders_skipped"], 1)
        self.assertEqual(data["subtitle_files_skipped"], 1)
        self.assertIn("Movie1", data["skipped_folders"])

    def test_recover_subtitle_folders_preserves_structure(self):
        """Test that subtitle recovery preserves folder structure"""
        folder = self.recycled_dir / "Movie1"
        folder.mkdir()
        (folder / "subtitle.srt").touch()

        # Create nested structure
        (folder / "subs").mkdir()
        (folder / "subs" / "en").mkdir()
        (folder / "subs" / "en" / "subtitle.srt").touch()
        (folder / "subs" / "fr").mkdir()
        (folder / "subs" / "fr" / "subtitle.srt").touch()

        response = client.post(
            "/api/v1/recover/subtitle-folders?dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Verify structure is preserved
        self.assertTrue((self.recovered_dir / "Movie1").exists())
        self.assertTrue(
            (self.recovered_dir / "Movie1" / "subtitle.srt").exists()
        )
        self.assertTrue(
            (
                self.recovered_dir / "Movie1" / "subs" / "en" / "subtitle.srt"
            ).exists()
        )
        self.assertTrue(
            (
                self.recovered_dir / "Movie1" / "subs" / "fr" / "subtitle.srt"
            ).exists()
        )

        self.assertEqual(data["subtitle_files_copied"], 3)
