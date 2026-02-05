import os
import shutil
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


def _is_case_insensitive(path: Path) -> bool:
    """Return True if the filesystem at path is case-insensitive."""
    try:
        (path / "case_check_a").touch()
        result = (path / "case_check_A").exists()
        (path / "case_check_a").unlink()
        return result
    except OSError:
        return False


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
        self.assertGreater(
            data["folders_moved"], 0
        )  # Reports what would be moved

        # Verify folders still exist (dry run doesn't actually move)
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

    def test_delete_source_if_match_exact_match_deletes_source(self):
        """When dest exists with exact match (only subtitles, same content), delete source."""
        (self.test_path / "subs_only").mkdir()
        (self.test_path / "subs_only" / "en.srt").write_text("sub")
        (self.test_path / "subs_only" / "Subs").mkdir()
        (self.test_path / "subs_only" / "Subs" / "fr.srt").write_text("sub")

        (self.migrated_path / "subs_only").mkdir()
        (self.migrated_path / "subs_only" / "en.srt").write_text("sub")
        (self.migrated_path / "subs_only" / "Subs").mkdir()
        (self.migrated_path / "subs_only" / "Subs" / "fr.srt").write_text(
            "sub"
        )

        response = client.post(
            "/api/v1/migrate/non-movie-folders?dry_run=false"
            "&delete_source_if_match=true"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["folders_deleted"], 1)
        self.assertIn("subs_only", data["deleted_folders"])
        self.assertFalse((self.test_path / "subs_only").exists())
        self.assertTrue((self.migrated_path / "subs_only" / "en.srt").exists())

    def test_delete_source_if_match_skips_when_not_only_subtitles(self):
        """When folder has non-subtitle files, skip delete even if dest matches."""
        (self.test_path / "has_nfo").mkdir()
        (self.test_path / "has_nfo" / "en.srt").write_text("sub")
        (self.test_path / "has_nfo" / "movie.nfo").write_text("nfo")

        (self.migrated_path / "has_nfo").mkdir()
        (self.migrated_path / "has_nfo" / "en.srt").write_text("sub")
        (self.migrated_path / "has_nfo" / "movie.nfo").write_text("nfo")

        response = client.post(
            "/api/v1/migrate/non-movie-folders?dry_run=false"
            "&delete_source_if_match=true"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["folders_deleted"], 0)
        self.assertGreater(data["folders_skipped"], 0)
        self.assertTrue((self.test_path / "has_nfo").exists())

    def test_delete_source_if_match_skips_when_contents_differ(self):
        """When file sizes differ, skip delete even if only subtitles."""
        (self.test_path / "diff_content").mkdir()
        (self.test_path / "diff_content" / "en.srt").write_text("a")

        (self.migrated_path / "diff_content").mkdir()
        (self.migrated_path / "diff_content" / "en.srt").write_text("ab")

        response = client.post(
            "/api/v1/migrate/non-movie-folders?dry_run=false"
            "&delete_source_if_match=true"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["folders_deleted"], 0)
        self.assertGreater(data["folders_skipped"], 0)
        self.assertTrue((self.test_path / "diff_content").exists())

    def test_delete_source_if_match_dry_run(self):
        """Dry run reports would delete when exact match."""
        (self.test_path / "would_delete").mkdir()
        (self.test_path / "would_delete" / "en.srt").write_text("x")

        (self.migrated_path / "would_delete").mkdir()
        (self.migrated_path / "would_delete" / "en.srt").write_text("x")

        response = client.post(
            "/api/v1/migrate/non-movie-folders?dry_run=true"
            "&delete_source_if_match=true"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["folders_deleted"], 1)
        self.assertIn("would_delete", data["deleted_folders"])
        self.assertTrue((self.test_path / "would_delete").exists())

    def test_delete_source_if_match_ignores_ds_store(self):
        """DS_Store in dest is ignored when comparing contents for delete."""
        (self.test_path / "with_ds_store").mkdir()
        (self.test_path / "with_ds_store" / "en.srt").write_text("x")

        (self.migrated_path / "with_ds_store").mkdir()
        (self.migrated_path / "with_ds_store" / "en.srt").write_text("x")
        (self.migrated_path / "with_ds_store" / ".DS_Store").write_text("junk")

        response = client.post(
            "/api/v1/migrate/non-movie-folders?dry_run=false"
            "&delete_source_if_match=true"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["folders_deleted"], 1)
        self.assertIn("with_ds_store", data["deleted_folders"])
        self.assertFalse((self.test_path / "with_ds_store").exists())

    def test_delete_source_if_match_ignores_ds_store_in_source(self):
        """DS_Store in source is ignored when checking only-subtitles for delete."""
        (self.test_path / "ds_store_in_src").mkdir()
        (self.test_path / "ds_store_in_src" / "en.srt").write_text("x")
        (self.test_path / "ds_store_in_src" / ".DS_Store").write_text("junk")

        (self.migrated_path / "ds_store_in_src").mkdir()
        (self.migrated_path / "ds_store_in_src" / "en.srt").write_text("x")

        response = client.post(
            "/api/v1/migrate/non-movie-folders?dry_run=false"
            "&delete_source_if_match=true"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["folders_deleted"], 1)
        self.assertIn("ds_store_in_src", data["deleted_folders"])
        self.assertFalse((self.test_path / "ds_store_in_src").exists())

    def test_delete_source_if_match_default_false(self):
        """Without delete_source_if_match, dest exists still skips (no delete)."""
        (self.test_path / "no_delete").mkdir()
        (self.test_path / "no_delete" / "en.srt").write_text("x")

        (self.migrated_path / "no_delete").mkdir()
        (self.migrated_path / "no_delete" / "en.srt").write_text("x")

        response = client.post(
            "/api/v1/migrate/non-movie-folders?dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["folders_deleted"], 0)
        self.assertGreater(data["folders_skipped"], 0)
        self.assertTrue((self.test_path / "no_delete").exists())

    def test_delete_source_if_match_symlink_removes_symlink(self):
        """When source is a symlink with exact match, unlink removes it (not rmtree)."""
        real_dir = self.test_path / "z_real_subs"
        real_dir.mkdir()
        (real_dir / "en.srt").write_text("x")

        symlink_path = self.test_path / "a_sym_subs"
        symlink_path.symlink_to(real_dir)

        (self.migrated_path / "a_sym_subs").mkdir()
        (self.migrated_path / "a_sym_subs" / "en.srt").write_text("x")

        response = client.post(
            "/api/v1/migrate/non-movie-folders?dry_run=false"
            "&delete_source_if_match=true"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["folders_deleted"], 1)
        self.assertIn("a_sym_subs", data["deleted_folders"])
        self.assertFalse(symlink_path.exists())
        # Real dir was moved to migrated (not deleted); symlink was unlinked only
        self.assertTrue(
            (self.migrated_path / "z_real_subs" / "en.srt").exists()
        )

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

    def test_migrate_excludes_empty_folders(self):
        """Test that empty folders are not included in migration (use empty-folders endpoint)"""
        client.post("/api/v1/migrate/non-movie-folders?dry_run=false")

        # Create an empty first-level folder
        (self.test_path / "empty_folder").mkdir()
        # Create a folder with files but no movies
        (self.test_path / "has_files_no_movies").mkdir()
        (self.test_path / "has_files_no_movies" / "readme.txt").touch()

        response = client.post(
            "/api/v1/migrate/non-movie-folders?dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertNotIn(
            "empty_folder",
            data["folders_to_migrate"],
            "Empty folders should not be migrated",
        )
        self.assertIn(
            "has_files_no_movies",
            data["folders_to_migrate"],
            "Folders with files but no movies should be migrated",
        )
        self.assertTrue((self.test_path / "empty_folder").exists())
        self.assertFalse((self.migrated_path / "empty_folder").exists())

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

    def test_migrate_skips_symlinks_pointing_outside_target(self):
        """Test that symlinks pointing outside target are skipped"""
        client.post("/api/v1/migrate/non-movie-folders?dry_run=false")

        # Create external dir with no movies
        external = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(external, ignore_errors=True))
        (external / "file.txt").touch()

        # Symlink in target pointing outside
        (self.test_path / "ext_link").symlink_to(external)

        response = client.post(
            "/api/v1/migrate/non-movie-folders?dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Should not include ext_link (symlink points outside target)
        self.assertNotIn("ext_link", data["folders_to_migrate"])
        self.assertNotIn("ext_link", data["moved_folders"])
        # External directory must still exist and be unchanged
        self.assertTrue(external.exists())
        self.assertTrue((external / "file.txt").exists())

    def test_merge_missing_files_copies_source_files_to_destination(self):
        """When merge_missing_files=True and dest exists, copy missing files."""
        (self.test_path / "merge_src").mkdir()
        (self.test_path / "merge_src" / "Subs").mkdir()
        (self.test_path / "merge_src" / "Subs" / "English.srt").write_text(
            "sub content"
        )
        (self.test_path / "merge_src" / "Subs" / "dut.srt").write_text(
            "dutch sub"
        )

        (self.migrated_path / "merge_src").mkdir()
        (self.migrated_path / "merge_src" / "movie.mkv").touch()

        response = client.post(
            "/api/v1/migrate/non-movie-folders?dry_run=false"
            "&merge_missing_files=true"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["folders_merged"], 1)
        self.assertEqual(data["files_merged"], 2)
        self.assertIn("merge_src", data["merged_folders"])

        self.assertTrue(
            (
                self.migrated_path / "merge_src" / "Subs" / "English.srt"
            ).exists()
        )
        self.assertTrue(
            (self.migrated_path / "merge_src" / "Subs" / "dut.srt").exists()
        )
        self.assertTrue(
            (self.migrated_path / "merge_src" / "movie.mkv").exists()
        )
        self.assertEqual(
            (
                self.migrated_path / "merge_src" / "Subs" / "English.srt"
            ).read_text(),
            "sub content",
        )
        self.assertTrue((self.test_path / "merge_src").exists())

    def test_merge_missing_files_delete_source_after_merge(self):
        """When delete_source_after_merge=True, delete source after copying."""
        (self.test_path / "merge_then_del").mkdir()
        (self.test_path / "merge_then_del" / "en.srt").write_text("sub")

        (self.migrated_path / "merge_then_del").mkdir()
        (self.migrated_path / "merge_then_del" / "movie.mkv").touch()

        response = client.post(
            "/api/v1/migrate/non-movie-folders?dry_run=false"
            "&merge_missing_files=true&delete_source_after_merge=true"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["folders_merged"], 1)
        self.assertEqual(data["folders_deleted"], 1)
        self.assertIn("merge_then_del", data["merged_folders"])
        self.assertIn("merge_then_del", data["deleted_folders"])

        self.assertTrue(
            (self.migrated_path / "merge_then_del" / "en.srt").exists()
        )
        self.assertFalse((self.test_path / "merge_then_del").exists())

    def test_merge_missing_files_skips_when_no_files_to_merge(self):
        """When dest has all source files, skip (no merge)."""
        (self.test_path / "no_merge").mkdir()
        (self.test_path / "no_merge" / "en.srt").write_text("x")

        (self.migrated_path / "no_merge").mkdir()
        (self.migrated_path / "no_merge" / "en.srt").write_text("x")

        response = client.post(
            "/api/v1/migrate/non-movie-folders?dry_run=false"
            "&merge_missing_files=true"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["folders_merged"], 0)
        self.assertEqual(data["files_merged"], 0)
        self.assertGreater(data["folders_skipped"], 0)
        self.assertIn("no_merge", data["skipped_folders"])

    def test_delete_source_when_nothing_to_merge(self):
        """When nothing to merge (source subset), delete source if requested."""
        (self.test_path / "redundant_src").mkdir()
        (self.test_path / "redundant_src" / "en.srt").write_text("x")

        (self.migrated_path / "redundant_src").mkdir()
        (self.migrated_path / "redundant_src" / "movie.mkv").touch()
        (self.migrated_path / "redundant_src" / "en.srt").write_text("x")

        response = client.post(
            "/api/v1/migrate/non-movie-folders?dry_run=false"
            "&merge_missing_files=true"
            "&delete_source_when_nothing_to_merge=true"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["folders_deleted"], 1)
        self.assertIn("redundant_src", data["deleted_folders"])
        self.assertFalse((self.test_path / "redundant_src").exists())
        self.assertTrue(
            (self.migrated_path / "redundant_src" / "movie.mkv").exists()
        )

    def test_delete_source_when_nothing_to_merge_dry_run(self):
        """Dry run reports would delete when nothing to merge."""
        (self.test_path / "would_del_redundant").mkdir()
        (self.test_path / "would_del_redundant" / "en.srt").write_text("x")

        (self.migrated_path / "would_del_redundant").mkdir()
        (self.migrated_path / "would_del_redundant" / "movie.mkv").touch()
        (self.migrated_path / "would_del_redundant" / "en.srt").write_text("x")

        response = client.post(
            "/api/v1/migrate/non-movie-folders?dry_run=true"
            "&merge_missing_files=true"
            "&delete_source_when_nothing_to_merge=true"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["folders_deleted"], 1)
        self.assertIn("would_del_redundant", data["deleted_folders"])
        self.assertTrue((self.test_path / "would_del_redundant").exists())

    def test_merge_missing_files_dry_run(self):
        """Dry run reports would merge without copying."""
        (self.test_path / "dry_merge").mkdir()
        (self.test_path / "dry_merge" / "extra.srt").write_text("extra")

        (self.migrated_path / "dry_merge").mkdir()
        (self.migrated_path / "dry_merge" / "movie.mkv").touch()

        response = client.post(
            "/api/v1/migrate/non-movie-folders?dry_run=true"
            "&merge_missing_files=true"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["folders_merged"], 1)
        self.assertEqual(data["files_merged"], 1)
        self.assertIn("dry_merge", data["merged_folders"])
        self.assertFalse(
            (self.migrated_path / "dry_merge" / "extra.srt").exists()
        )
        self.assertTrue((self.test_path / "dry_merge").exists())

    def test_merge_copy_failure_skips_delete_preserves_source(self):
        """When merge copy fails, do not delete source - preserve data."""
        (self.test_path / "merge_fail").mkdir()
        (self.test_path / "merge_fail" / "Subs").mkdir()
        (self.test_path / "merge_fail" / "Subs" / "English.srt").write_text(
            "sub"
        )

        (self.migrated_path / "merge_fail").mkdir()
        (self.migrated_path / "merge_fail" / "movie.mkv").touch()
        (self.migrated_path / "merge_fail" / "Subs").write_text("not a dir")
        # Subs is a file, so copying Subs/English.srt will fail

        response = client.post(
            "/api/v1/migrate/non-movie-folders?dry_run=false"
            "&merge_missing_files=true&delete_source_after_merge=true"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["folders_merged"], 1)
        self.assertGreater(data["errors"], 0)
        self.assertEqual(data["folders_deleted"], 0)
        self.assertIn("merge_fail", data["merged_folders"])
        self.assertNotIn("merge_fail", data["deleted_folders"])
        self.assertTrue((self.test_path / "merge_fail").exists())
        self.assertTrue(
            (self.test_path / "merge_fail" / "Subs" / "English.srt").exists()
        )

    def test_merge_partial_copy_failure_skips_delete(self):
        """When some files fail to copy, do not delete source."""
        (self.test_path / "partial_fail").mkdir()
        (self.test_path / "partial_fail" / "ok.srt").write_text("ok")
        (self.test_path / "partial_fail" / "Subs").mkdir()
        (self.test_path / "partial_fail" / "Subs" / "fail.srt").write_text(
            "fail"
        )

        (self.migrated_path / "partial_fail").mkdir()
        (self.migrated_path / "partial_fail" / "movie.mkv").touch()
        (self.migrated_path / "partial_fail" / "Subs").write_text("blocker")
        # ok.srt can copy; Subs/fail.srt will fail (Subs is file)

        response = client.post(
            "/api/v1/migrate/non-movie-folders?dry_run=false"
            "&merge_missing_files=true&delete_source_after_merge=true"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["folders_merged"], 1)
        self.assertGreater(data["files_merged"], 0)
        self.assertGreater(data["errors"], 0)
        self.assertEqual(data["folders_deleted"], 0)
        self.assertTrue((self.test_path / "partial_fail").exists())
        self.assertTrue(
            (self.migrated_path / "partial_fail" / "ok.srt").exists()
        )

    def test_merge_case_insensitive_skips_existing_different_casing(self):
        """On case-insensitive FS, dest with different casing is not overwritten."""
        (self.test_path / "case_merge").mkdir()
        (self.test_path / "case_merge" / "Subs").mkdir()
        (self.test_path / "case_merge" / "Subs" / "English.srt").write_text(
            "from source"
        )

        (self.migrated_path / "case_merge").mkdir()
        (self.migrated_path / "case_merge" / "movie.mkv").touch()
        (self.migrated_path / "case_merge" / "subs").mkdir()
        (
            self.migrated_path / "case_merge" / "subs" / "english.srt"
        ).write_text("existing in dest")

        response = client.post(
            "/api/v1/migrate/non-movie-folders?dry_run=false"
            "&merge_missing_files=true"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        if _is_case_insensitive(self.test_path):
            self.assertEqual(
                data["files_merged"],
                0,
                "Should not overwrite on case-insensitive FS",
            )
            dest_content = (
                self.migrated_path / "case_merge" / "subs" / "english.srt"
            ).read_text()
            self.assertEqual(
                dest_content,
                "existing in dest",
                "Dest file must not be overwritten",
            )
        else:
            self.assertEqual(data["files_merged"], 1)
            self.assertTrue(
                (
                    self.migrated_path / "case_merge" / "Subs" / "English.srt"
                ).exists()
            )

    def test_migrate_moves_symlink_not_target(self):
        """Test that when migrating a symlink (pointing inside target), the symlink is moved, not its target"""
        client.post("/api/v1/migrate/non-movie-folders?dry_run=false")

        # Real folder with no movies inside target
        (self.test_path / "real_folder").mkdir()
        (self.test_path / "real_folder" / "file.txt").touch()
        # Symlink inside target pointing to that folder
        (self.test_path / "link_to_real").symlink_to(
            self.test_path / "real_folder"
        )

        response = client.post(
            "/api/v1/migrate/non-movie-folders?dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Both real_folder and link_to_real have no movies; both get migrated
        self.assertIn("real_folder", data["moved_folders"])
        self.assertIn("link_to_real", data["moved_folders"])
        # real_folder content moved to migrated
        self.assertTrue(
            (self.migrated_path / "real_folder" / "file.txt").exists()
        )
        # link_to_real (the symlink) moved to migrated; use lexists because
        # if real_folder was moved first the symlink is broken (target gone)
        # and .exists() would be False since it follows the link
        migrated_link = self.migrated_path / "link_to_real"
        self.assertTrue(
            os.path.lexists(str(migrated_link)),
            f"Symlink should exist at {migrated_link} (lexists)",
        )
        self.assertFalse((self.test_path / "real_folder").exists())
        self.assertFalse(os.path.lexists(str(self.test_path / "link_to_real")))


if __name__ == "__main__":
    unittest.main()
