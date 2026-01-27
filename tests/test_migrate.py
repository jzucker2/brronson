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


class TestNonMovieFolderMigration(unittest.TestCase):
    """Test the non-movie folder migration functionality"""

    def setUp(self):
        """Set up test directory structure"""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)
        self.migrated_dir = tempfile.mkdtemp()
        self.migrated_path = Path(self.migrated_dir)

        # Create directory structure with folders with and without movie files
        # Folder with movie file
        (self.test_path / "has_movie").mkdir()
        (self.test_path / "has_movie" / "movie.mp4").touch()

        # Folder with only subtitle files (no movie)
        (self.test_path / "only_subtitles").mkdir()
        (self.test_path / "only_subtitles" / "subtitle.srt").touch()

        # Folder with only text files (no movie)
        (self.test_path / "only_text").mkdir()
        (self.test_path / "only_text" / "readme.txt").touch()

        # Folder with mixed files but no movie
        (self.test_path / "mixed_no_movie").mkdir()
        (self.test_path / "mixed_no_movie" / "file1.txt").touch()
        (self.test_path / "mixed_no_movie" / "file2.jpg").touch()

        # Nested folder without movie
        (self.test_path / "nested").mkdir()
        (self.test_path / "nested" / "subfolder").mkdir()
        (self.test_path / "nested" / "subfolder" / "file.txt").touch()

        # Set environment variables for testing
        self.original_target_dir = os.environ.get("TARGET_DIRECTORY")
        self.original_migrated_dir = os.environ.get(
            "MIGRATED_MOVIES_DIRECTORY"
        )
        os.environ["TARGET_DIRECTORY"] = self.test_dir
        os.environ["MIGRATED_MOVIES_DIRECTORY"] = self.migrated_dir

        # Clear Prometheus default registry
        import prometheus_client

        prometheus_client.REGISTRY._names_to_collectors.clear()

    def tearDown(self):
        """Clean up test directories"""
        import shutil

        # Restore environment variables
        if self.original_target_dir is not None:
            os.environ["TARGET_DIRECTORY"] = self.original_target_dir
        elif "TARGET_DIRECTORY" in os.environ:
            del os.environ["TARGET_DIRECTORY"]

        if self.original_migrated_dir is not None:
            os.environ["MIGRATED_MOVIES_DIRECTORY"] = (
                self.original_migrated_dir
            )
        elif "MIGRATED_MOVIES_DIRECTORY" in os.environ:
            del os.environ["MIGRATED_MOVIES_DIRECTORY"]

        # Clean up test directories
        if self.test_path.exists():
            shutil.rmtree(self.test_path)
        if self.migrated_path.exists():
            shutil.rmtree(self.migrated_path)

        # Clear Prometheus default registry
        import prometheus_client

        prometheus_client.REGISTRY._names_to_collectors.clear()

    def test_migrate_non_movie_folders_dry_run(self):
        """Test migrating folders without movie files in dry run mode"""
        response = client.post("/api/v1/migrate/non-movie-folders")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertTrue(data["dry_run"])
        self.assertGreater(data["folders_found"], 0)
        self.assertEqual(data["folders_moved"], 0)  # Dry run doesn't move

        # Verify folders still exist (dry run)
        self.assertTrue((self.test_path / "only_subtitles").exists())
        self.assertTrue((self.test_path / "only_text").exists())
        self.assertTrue(
            (self.test_path / "has_movie").exists()
        )  # Should not be in list

    def test_migrate_non_movie_folders_actual_move(self):
        """Test actually moving folders without movie files"""
        response = client.post(
            "/api/v1/migrate/non-movie-folders?dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertFalse(data["dry_run"])
        self.assertGreater(data["folders_moved"], 0)

        # Verify folders were moved
        self.assertFalse((self.test_path / "only_subtitles").exists())
        self.assertFalse((self.test_path / "only_text").exists())
        self.assertTrue((self.migrated_path / "only_subtitles").exists())
        self.assertTrue((self.migrated_path / "only_text").exists())

        # Verify folder with movie was not moved
        self.assertTrue((self.test_path / "has_movie").exists())

    def test_migrate_non_movie_folders_batch_size(self):
        """Test that batch_size parameter limits folders scanned and moved"""
        # First, clean up existing folders from setUp
        client.post("/api/v1/migrate/non-movie-folders?dry_run=false")

        # Create multiple folders without movies
        for i in range(1, 6):
            folder_path = self.test_path / f"batch_migrate{i}"
            folder_path.mkdir()
            (folder_path / f"file{i}.txt").touch()

        # Set batch_size to 3
        response = client.post(
            "/api/v1/migrate/non-movie-folders?dry_run=false&batch_size=3"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # With batch_size=3, scan stops after finding 3 folders
        # All 3 found folders should be moved
        self.assertEqual(data["batch_size"], 3)
        self.assertEqual(data["folders_found"], 3)
        self.assertEqual(data["folders_moved"], 3)
        self.assertTrue(data["batch_limit_reached"])

    def test_migrate_non_movie_folders_skip_existing(self):
        """Test that existing destination folders are skipped"""
        # Create a folder without movie
        (self.test_path / "to_migrate").mkdir()
        (self.test_path / "to_migrate" / "file.txt").touch()

        # Create destination folder with same name
        (self.migrated_path / "to_migrate").mkdir()
        (self.migrated_path / "to_migrate" / "existing.txt").touch()

        response = client.post(
            "/api/v1/migrate/non-movie-folders?dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Should be skipped, not moved
        self.assertGreater(data["folders_skipped"], 0)
        self.assertTrue((self.test_path / "to_migrate").exists())
        self.assertTrue((self.migrated_path / "to_migrate").exists())

    def test_migrate_non_movie_folders_nested(self):
        """Test that first-level folders with nested subdirectories are migrated"""
        response = client.post(
            "/api/v1/migrate/non-movie-folders?dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Should find first-level "nested" folder (which contains subfolder)
        # The entire "nested" folder should be migrated, not just "subfolder"
        folder_names = [Path(f).name for f in data["folders_to_migrate"]]
        self.assertIn("nested", folder_names)
        # "subfolder" is nested inside "nested", so it won't be processed separately
        self.assertNotIn("subfolder", folder_names)

    def test_migrate_non_movie_folders_metrics(self):
        """Test that metrics are recorded correctly"""
        response = client.post(
            "/api/v1/migrate/non-movie-folders?dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check metrics endpoint
        metrics_response = client.get("/metrics")
        self.assertEqual(metrics_response.status_code, 200)
        metrics_text = metrics_response.text

        # Verify metrics are present
        self.assertIn("brronson_migrate_folders_found_total", metrics_text)
        self.assertIn("brronson_migrate_folders_moved_total", metrics_text)

        # Verify metric values match response
        target_dir_normalized = normalize_path_for_metrics(self.test_dir)
        migrated_dir_normalized = normalize_path_for_metrics(self.migrated_dir)

        assert_metric_with_labels(
            metrics_text,
            "brronson_migrate_folders_found_total",
            {
                "target_directory": target_dir_normalized,
                "dry_run": "false",
            },
            str(data["folders_found"]),
        )

        assert_metric_with_labels(
            metrics_text,
            "brronson_migrate_folders_moved_total",
            {
                "target_directory": target_dir_normalized,
                "migrated_directory": migrated_dir_normalized,
                "dry_run": "false",
            },
            str(data["folders_moved"]),
        )

    def test_migrate_first_level_subdirectories_only(self):
        """Test that only first-level subdirectories are migrated"""
        # First, clean up existing folders from setUp
        client.post("/api/v1/migrate/non-movie-folders?dry_run=false")

        # Create first-level subdirectories
        # "folder_a" has no movies - should be migrated
        (self.test_path / "folder_a").mkdir()
        (self.test_path / "folder_a" / "file1.txt").touch()

        # "folder_b" has a movie - should NOT be migrated
        (self.test_path / "folder_b").mkdir()
        (self.test_path / "folder_b" / "movie.mp4").touch()

        # "folder_c" has nested subdir with no movies - entire folder_a should be migrated
        (self.test_path / "folder_c").mkdir()
        (self.test_path / "folder_c" / "sub").mkdir()
        (self.test_path / "folder_c" / "sub" / "file2.txt").touch()

        response = client.post(
            "/api/v1/migrate/non-movie-folders?dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Should migrate folder_a and folder_c (no movies), but not folder_b (has movie)
        self.assertEqual(data["folders_moved"], 2)
        self.assertIn("folder_a", data["moved_folders"])
        self.assertIn("folder_c", data["moved_folders"])
        self.assertNotIn("folder_b", data["moved_folders"])

        # Verify migrated folders
        self.assertTrue((self.migrated_path / "folder_a").exists())
        self.assertTrue((self.migrated_path / "folder_c").exists())
        self.assertTrue((self.migrated_path / "folder_c" / "sub").exists())
        self.assertFalse((self.migrated_path / "folder_b").exists())

        # Verify original folders are gone (except folder_b which has a movie)
        self.assertFalse((self.test_path / "folder_a").exists())
        self.assertFalse((self.test_path / "folder_c").exists())
        self.assertTrue((self.test_path / "folder_b").exists())

    def test_migrate_excludes_migrated_directory(self):
        """Test that migrated directory is excluded from scan if inside target"""
        # First, clean up existing folders from setUp
        client.post("/api/v1/migrate/non-movie-folders?dry_run=false")

        # Set migrated directory inside target directory
        nested_migrated = self.test_path / "migrated"
        nested_migrated.mkdir()

        # Create a folder without movie files
        (self.test_path / "to_migrate").mkdir()
        (self.test_path / "to_migrate" / "file.txt").touch()

        # Update environment to use nested migrated directory
        os.environ["MIGRATED_MOVIES_DIRECTORY"] = str(nested_migrated)

        try:
            response = client.post(
                "/api/v1/migrate/non-movie-folders?dry_run=false"
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()

            # Should find and move the folder, but NOT the migrated directory itself
            self.assertGreater(data["folders_moved"], 0)
            self.assertNotIn("migrated", data["moved_folders"])

            # Verify migrated directory still exists (wasn't moved into itself)
            self.assertTrue(nested_migrated.exists())
            # Verify the folder was moved to the migrated directory
            self.assertTrue((nested_migrated / "to_migrate").exists())
        finally:
            # Restore original migrated directory
            if self.original_migrated_dir is not None:
                os.environ["MIGRATED_MOVIES_DIRECTORY"] = (
                    self.original_migrated_dir
                )
            elif "MIGRATED_MOVIES_DIRECTORY" in os.environ:
                del os.environ["MIGRATED_MOVIES_DIRECTORY"]


if __name__ == "__main__":
    unittest.main()
