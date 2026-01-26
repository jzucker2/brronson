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


class TestEmptyFoldersCleanup(unittest.TestCase):
    """Test the empty folder cleanup functionality"""

    def setUp(self):
        """Set up test directory structure"""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

        # Create directory structure with empty and non-empty folders
        # Non-empty folder with files
        (self.test_path / "non_empty").mkdir()
        (self.test_path / "non_empty" / "file.txt").touch()

        # Empty folder at root level
        (self.test_path / "empty1").mkdir()

        # Nested empty folders
        (self.test_path / "nested").mkdir()
        (self.test_path / "nested" / "empty2").mkdir()
        (self.test_path / "nested" / "empty2" / "empty3").mkdir()

        # Folder with empty subfolder (should delete subfolder but not parent)
        (self.test_path / "parent").mkdir()
        (self.test_path / "parent" / "file.txt").touch()
        (self.test_path / "parent" / "empty_child").mkdir()

        # Set environment variable for testing
        self.original_target_dir = os.environ.get("TARGET_DIRECTORY")
        os.environ["TARGET_DIRECTORY"] = self.test_dir

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
        """Clean up test directory and restore environment"""
        import shutil

        shutil.rmtree(self.test_dir, ignore_errors=True)

        if self.original_target_dir is not None:
            os.environ["TARGET_DIRECTORY"] = self.original_target_dir
        elif "TARGET_DIRECTORY" in os.environ:
            del os.environ["TARGET_DIRECTORY"]

    def test_cleanup_empty_folders_dry_run(self):
        """Test empty folder cleanup endpoint in dry run mode (default)"""
        response = client.post("/api/v1/cleanup/empty-folders")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check response structure
        self.assertIn("directory", data)
        self.assertIn("dry_run", data)
        self.assertIn("batch_size", data)
        self.assertIn("empty_folders_found", data)
        self.assertIn("empty_folders_removed", data)
        self.assertIn("errors", data)
        self.assertIn("batch_limit_reached", data)
        self.assertIn("remaining_folders", data)
        self.assertIn("empty_folders", data)
        self.assertIn("removed_folders", data)
        self.assertIn("error_details", data)

        # Check expected results (dry run)
        self.assertTrue(data["dry_run"])
        self.assertGreater(data["empty_folders_found"], 0)
        self.assertEqual(
            data["empty_folders_removed"], 0
        )  # No folders removed in dry run
        self.assertEqual(data["errors"], 0)

        # Verify folders still exist (dry run)
        self.assertTrue((self.test_path / "empty1").exists())
        self.assertTrue((self.test_path / "nested" / "empty2").exists())
        self.assertTrue(
            (self.test_path / "nested" / "empty2" / "empty3").exists()
        )
        self.assertTrue((self.test_path / "parent" / "empty_child").exists())

    def test_cleanup_empty_folders_actual_removal(self):
        """Test empty folder cleanup endpoint with actual removal"""
        response = client.post("/api/v1/cleanup/empty-folders?dry_run=false")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check expected results (actual removal)
        self.assertFalse(data["dry_run"])
        self.assertGreater(data["empty_folders_found"], 0)
        self.assertGreater(data["empty_folders_removed"], 0)
        self.assertEqual(data["errors"], 0)

        # Verify empty folders are removed
        self.assertFalse((self.test_path / "empty1").exists())
        self.assertFalse((self.test_path / "nested" / "empty2").exists())
        self.assertFalse(
            (self.test_path / "nested" / "empty2" / "empty3").exists()
        )
        self.assertFalse((self.test_path / "parent" / "empty_child").exists())

        # Verify non-empty folders still exist
        self.assertTrue((self.test_path / "non_empty").exists())
        self.assertTrue((self.test_path / "non_empty" / "file.txt").exists())
        self.assertTrue((self.test_path / "parent").exists())
        self.assertTrue((self.test_path / "parent" / "file.txt").exists())

        # Verify nested folder structure is cleaned up correctly
        # After removing empty3, empty2 should become empty and be removed
        # After removing empty2, nested might still exist if it has other contents
        # (but in our test setup, nested should be empty after removing empty2/empty3)
        self.assertFalse((self.test_path / "nested").exists())

    def test_cleanup_empty_folders_nested_structure(self):
        """Test that nested empty folders are handled correctly"""
        # Create a deeper nested structure
        (self.test_path / "deep").mkdir()
        (self.test_path / "deep" / "level1").mkdir()
        (self.test_path / "deep" / "level1" / "level2").mkdir()
        (self.test_path / "deep" / "level1" / "level2" / "level3").mkdir()

        response = client.post("/api/v1/cleanup/empty-folders?dry_run=false")
        self.assertEqual(response.status_code, 200)

        # All nested empty folders should be removed
        self.assertFalse((self.test_path / "deep").exists())
        self.assertFalse((self.test_path / "deep" / "level1").exists())
        self.assertFalse(
            (self.test_path / "deep" / "level1" / "level2").exists()
        )
        self.assertFalse(
            (self.test_path / "deep" / "level1" / "level2" / "level3").exists()
        )

    def test_cleanup_empty_folders_no_empty_folders(self):
        """Test empty folder cleanup when there are no empty folders"""
        # Remove all empty folders first
        import shutil

        shutil.rmtree(self.test_path / "empty1", ignore_errors=True)
        shutil.rmtree(self.test_path / "nested", ignore_errors=True)
        shutil.rmtree(
            self.test_path / "parent" / "empty_child", ignore_errors=True
        )

        response = client.post("/api/v1/cleanup/empty-folders")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Should find no empty folders
        self.assertEqual(data["empty_folders_found"], 0)
        self.assertEqual(data["empty_folders_removed"], 0)
        self.assertEqual(data["errors"], 0)
        self.assertEqual(len(data["empty_folders"]), 0)

    def test_cleanup_empty_folders_nonexistent_directory(self):
        """Test empty folder cleanup with nonexistent directory"""
        os.environ["TARGET_DIRECTORY"] = "/nonexistent/dir"

        response = client.post("/api/v1/cleanup/empty-folders")
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("not found", data["detail"])

        # Restore test directory
        os.environ["TARGET_DIRECTORY"] = self.test_dir

    def test_cleanup_empty_folders_system_directory_protection(self):
        """Test that system directories are protected"""
        os.environ["TARGET_DIRECTORY"] = "/etc"

        response = client.post("/api/v1/cleanup/empty-folders")
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("protected system location", data["detail"])

        # Restore test directory
        os.environ["TARGET_DIRECTORY"] = self.test_dir

    def test_cleanup_empty_folders_metrics(self):
        """Test that empty folder cleanup records metrics"""
        response = client.post("/api/v1/cleanup/empty-folders")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check metrics
        metrics_response = client.get("/metrics")
        metrics_text = metrics_response.text

        # Should have empty folder metrics
        self.assertIn("brronson_empty_folders_found_total", metrics_text)
        self.assertIn(
            "brronson_empty_folders_operation_duration_seconds", metrics_text
        )

        target_path_resolved = normalize_path_for_metrics(self.test_path)

        # Check folders found metric (use actual value from response)
        expected_value = f"{float(data['empty_folders_found'])}"
        assert_metric_with_labels(
            metrics_text,
            "brronson_empty_folders_found_total",
            {
                "target_directory": target_path_resolved,
                "dry_run": "true",
            },
            expected_value,
        )

    def test_cleanup_empty_folders_metrics_with_removal(self):
        """Test that empty folder cleanup records removal metrics"""
        response = client.post("/api/v1/cleanup/empty-folders?dry_run=false")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check metrics
        metrics_response = client.get("/metrics")
        metrics_text = metrics_response.text

        # Should have removal metrics
        self.assertIn("brronson_empty_folders_removed_total", metrics_text)

        target_path_resolved = normalize_path_for_metrics(self.test_path)

        # Check folders removed metric (use actual value from response)
        expected_value = f"{float(data['empty_folders_removed'])}"
        assert_metric_with_labels(
            metrics_text,
            "brronson_empty_folders_removed_total",
            {
                "target_directory": target_path_resolved,
                "dry_run": "false",
            },
            expected_value,
        )

    def test_cleanup_empty_folders_preserves_non_empty(self):
        """Test that non-empty folders are preserved"""
        # Create a folder with only hidden files (should still be considered non-empty)
        (self.test_path / "hidden_files").mkdir()
        (self.test_path / "hidden_files" / ".hidden").touch()

        response = client.post("/api/v1/cleanup/empty-folders?dry_run=false")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Folder with hidden file should not be removed
        self.assertTrue((self.test_path / "hidden_files").exists())
        self.assertTrue((self.test_path / "hidden_files" / ".hidden").exists())

        # Verify it wasn't in the list of empty folders
        empty_folder_paths = [Path(f).name for f in data["empty_folders"]]
        self.assertNotIn("hidden_files", empty_folder_paths)

    def test_cleanup_empty_folders_batch_size(self):
        """Test that batch_size parameter limits folders deleted"""
        # First, clean up existing empty folders from setUp
        client.post("/api/v1/cleanup/empty-folders?dry_run=false")

        # Create multiple empty folders for batch testing
        for i in range(1, 6):
            folder_path = self.test_path / f"batch_empty{i}"
            folder_path.mkdir(exist_ok=True)

        # Set batch_size to 3
        response = client.post(
            "/api/v1/cleanup/empty-folders?dry_run=false&batch_size=3"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Should have deleted exactly 3 folders
        self.assertEqual(data["batch_size"], 3)
        self.assertEqual(data["empty_folders_removed"], 3)
        self.assertGreaterEqual(data["empty_folders_found"], 5)
        self.assertTrue(data["batch_limit_reached"])
        self.assertGreaterEqual(data["remaining_folders"], 2)

        # Verify only 3 batch_empty folders were deleted
        deleted_count = sum(
            1
            for i in range(1, 6)
            if not (self.test_path / f"batch_empty{i}").exists()
        )
        self.assertEqual(deleted_count, 3)

    def test_cleanup_empty_folders_batch_size_dry_run(self):
        """Test that batch_size works in dry run mode"""
        # First, clean up existing empty folders from setUp
        client.post("/api/v1/cleanup/empty-folders?dry_run=false")

        # Create multiple empty folders for batch testing
        for i in range(1, 4):
            folder_path = self.test_path / f"batch_dry_run{i}"
            folder_path.mkdir(exist_ok=True)

        response = client.post(
            "/api/v1/cleanup/empty-folders?dry_run=true&batch_size=2"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Dry run should show batch limit would be reached
        self.assertTrue(data["dry_run"])
        self.assertEqual(data["batch_size"], 2)
        self.assertGreaterEqual(data["empty_folders_found"], 3)
        self.assertTrue(data["batch_limit_reached"])
        self.assertGreaterEqual(data["remaining_folders"], 1)

        # Verify folders still exist (dry run)
        for i in range(1, 4):
            self.assertTrue((self.test_path / f"batch_dry_run{i}").exists())

    def test_cleanup_empty_folders_batch_size_validation(self):
        """Test that batch_size validation rejects zero and negative values"""
        # Test with batch_size=0
        response = client.post(
            "/api/v1/cleanup/empty-folders?dry_run=false&batch_size=0"
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("batch_size must be a positive integer", data["detail"])

        # Test with negative batch_size
        response = client.post(
            "/api/v1/cleanup/empty-folders?dry_run=false&batch_size=-1"
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("batch_size must be a positive integer", data["detail"])

    def test_cleanup_empty_folders_reentrant(self):
        """Test that empty folder cleanup is re-entrant - can resume from where it stopped"""
        # First, clean up existing empty folders from setUp
        client.post("/api/v1/cleanup/empty-folders?dry_run=false")

        # Create multiple empty folders for reentrant testing
        for i in range(1, 6):
            folder_path = self.test_path / f"reentrant_empty{i}"
            folder_path.mkdir(exist_ok=True)

        # First request: delete 2 folders with batch_size=2
        response1 = client.post(
            "/api/v1/cleanup/empty-folders?dry_run=false&batch_size=2"
        )
        self.assertEqual(response1.status_code, 200)
        data1 = response1.json()

        self.assertEqual(data1["empty_folders_removed"], 2)
        self.assertTrue(data1["batch_limit_reached"])
        self.assertGreaterEqual(data1["remaining_folders"], 3)

        # Second request: should continue and delete next 2 folders
        response2 = client.post(
            "/api/v1/cleanup/empty-folders?dry_run=false&batch_size=2"
        )
        self.assertEqual(response2.status_code, 200)
        data2 = response2.json()

        # Should delete 2 more folders (batch_size=2)
        self.assertEqual(data2["empty_folders_removed"], 2)
        self.assertTrue(data2["batch_limit_reached"])
        self.assertGreaterEqual(data2["remaining_folders"], 1)

        # Third request: should finish deleting remaining folders
        response3 = client.post(
            "/api/v1/cleanup/empty-folders?dry_run=false&batch_size=2"
        )
        self.assertEqual(response3.status_code, 200)
        data3 = response3.json()

        # Should delete the last folder
        self.assertGreaterEqual(data3["empty_folders_removed"], 1)
        self.assertFalse(data3["batch_limit_reached"])

        # Total deleted should be all 5 reentrant_empty folders
        total_deleted = (
            data1["empty_folders_removed"]
            + data2["empty_folders_removed"]
            + data3["empty_folders_removed"]
        )
        self.assertGreaterEqual(total_deleted, 5)

        # Verify all reentrant_empty folders were deleted
        for i in range(1, 6):
            self.assertFalse((self.test_path / f"reentrant_empty{i}").exists())

    def test_target_directory_never_deleted(self):
        """Test that the target directory itself can never be deleted, even if empty"""
        # First, clean up existing empty folders from setUp
        client.post("/api/v1/cleanup/empty-folders?dry_run=false")

        # Create a scenario where the target directory would appear empty:
        # 1. Create only empty subdirectories
        # 2. Delete all of them
        # 3. Verify target directory still exists

        # Create multiple nested empty folders
        (self.test_path / "only_empty1").mkdir()
        (self.test_path / "only_empty2").mkdir()
        (self.test_path / "only_empty3" / "nested").mkdir(parents=True)

        # Verify target directory exists before cleanup
        self.assertTrue(self.test_path.exists())
        self.assertTrue(self.test_path.is_dir())

        # Run cleanup - should delete all empty subdirectories
        response = client.post("/api/v1/cleanup/empty-folders?dry_run=false")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # All empty subdirectories should be deleted
        self.assertGreaterEqual(data["empty_folders_removed"], 3)
        self.assertFalse((self.test_path / "only_empty1").exists())
        self.assertFalse((self.test_path / "only_empty2").exists())
        self.assertFalse((self.test_path / "only_empty3").exists())

        # CRITICAL: Target directory itself must still exist
        self.assertTrue(
            self.test_path.exists(),
            "Target directory must never be deleted, even if all subdirectories are empty",
        )
        self.assertTrue(
            self.test_path.is_dir(),
            "Target directory must remain a directory",
        )

        # Run cleanup again - target directory should still be empty of subdirectories
        # but should not be deleted itself
        response2 = client.post("/api/v1/cleanup/empty-folders?dry_run=false")
        self.assertEqual(response2.status_code, 200)
        data2 = response2.json()

        # Should find no more empty folders (target directory excluded)
        self.assertEqual(data2["empty_folders_found"], 0)
        self.assertEqual(data2["empty_folders_removed"], 0)

        # Target directory must still exist
        self.assertTrue(
            self.test_path.exists(),
            "Target directory must still exist after second cleanup",
        )

        # Test with dry_run as well
        response3 = client.post("/api/v1/cleanup/empty-folders?dry_run=true")
        self.assertEqual(response3.status_code, 200)
        data3 = response3.json()

        # Should find no empty folders (target directory excluded)
        self.assertEqual(data3["empty_folders_found"], 0)

        # Target directory must still exist
        self.assertTrue(
            self.test_path.exists(),
            "Target directory must still exist after dry run",
        )

    def test_empty_folder_detection_with_broken_symlink(self):
        """Test that folders containing broken symlinks are not marked as empty"""
        # First, clean up existing empty folders from setUp
        client.post("/api/v1/cleanup/empty-folders?dry_run=false")

        # Create a folder with a broken symlink
        folder_with_symlink = self.test_path / "folder_with_broken_symlink"
        folder_with_symlink.mkdir()

        # Create a broken symlink (points to non-existent file)
        broken_symlink = folder_with_symlink / "broken_link"
        broken_symlink.symlink_to("/nonexistent/path/to/file")

        # Verify symlink exists but is broken
        self.assertTrue(broken_symlink.is_symlink())
        self.assertFalse(broken_symlink.exists())

        # Run cleanup - should NOT mark folder as empty
        response = client.post("/api/v1/cleanup/empty-folders?dry_run=true")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Folder should NOT be in empty folders list
        empty_folder_names = [Path(f).name for f in data["empty_folders"]]
        self.assertNotIn(
            "folder_with_broken_symlink",
            empty_folder_names,
            "Folder with broken symlink should not be marked as empty",
        )

        # Folder should still exist
        self.assertTrue(folder_with_symlink.exists())

        # Clean up
        broken_symlink.unlink()
        folder_with_symlink.rmdir()

    def test_empty_folder_detection_with_valid_symlink(self):
        """Test that folders containing valid symlinks are not marked as empty"""
        # First, clean up existing empty folders from setUp
        client.post("/api/v1/cleanup/empty-folders?dry_run=false")

        # Create a folder with a valid symlink
        folder_with_symlink = self.test_path / "folder_with_valid_symlink"
        folder_with_symlink.mkdir()

        # Create a target file
        target_file = self.test_path / "target_file.txt"
        target_file.write_text("test content")

        # Create a valid symlink
        valid_symlink = folder_with_symlink / "valid_link"
        valid_symlink.symlink_to(target_file)

        # Verify symlink exists and is valid
        self.assertTrue(valid_symlink.is_symlink())
        self.assertTrue(valid_symlink.exists())

        # Run cleanup - should NOT mark folder as empty
        response = client.post("/api/v1/cleanup/empty-folders?dry_run=true")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Folder should NOT be in empty folders list
        empty_folder_names = [Path(f).name for f in data["empty_folders"]]
        self.assertNotIn(
            "folder_with_valid_symlink",
            empty_folder_names,
            "Folder with valid symlink should not be marked as empty",
        )

        # Folder should still exist
        self.assertTrue(folder_with_symlink.exists())

        # Clean up
        valid_symlink.unlink()
        target_file.unlink()
        folder_with_symlink.rmdir()

    @unittest.skipUnless(
        hasattr(os, "mkfifo"), "Named pipes not supported on this platform"
    )
    def test_empty_folder_detection_with_named_pipe(self):
        """Test that folders containing named pipes are not marked as empty"""
        # First, clean up existing empty folders from setUp
        client.post("/api/v1/cleanup/empty-folders?dry_run=false")

        # Create a folder with a named pipe
        folder_with_pipe = self.test_path / "folder_with_pipe"
        folder_with_pipe.mkdir()

        # Create a named pipe (FIFO)
        pipe_path = folder_with_pipe / "test_pipe"
        os.mkfifo(str(pipe_path))

        # Verify pipe exists
        self.assertTrue(pipe_path.exists())

        # Run cleanup - should NOT mark folder as empty
        response = client.post("/api/v1/cleanup/empty-folders?dry_run=true")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Folder should NOT be in empty folders list
        empty_folder_names = [Path(f).name for f in data["empty_folders"]]
        self.assertNotIn(
            "folder_with_pipe",
            empty_folder_names,
            "Folder with named pipe should not be marked as empty",
        )

        # Folder should still exist
        self.assertTrue(folder_with_pipe.exists())

        # Clean up
        pipe_path.unlink()
        folder_with_pipe.rmdir()

    def test_empty_folder_detection_with_special_files(self):
        """Test that folders containing only special files are not marked as empty"""
        # First, clean up existing empty folders from setUp
        client.post("/api/v1/cleanup/empty-folders?dry_run=false")

        # Create a folder that will only contain special files
        folder_with_special = self.test_path / "folder_with_special"
        folder_with_special.mkdir()

        # Create a broken symlink (special file type)
        broken_symlink = folder_with_special / "broken"
        broken_symlink.symlink_to("/nonexistent")

        # Verify broken symlink exists
        self.assertTrue(broken_symlink.is_symlink())
        self.assertFalse(broken_symlink.exists())

        # Run cleanup - should NOT mark folder as empty
        response = client.post("/api/v1/cleanup/empty-folders?dry_run=true")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Folder should NOT be in empty folders list
        empty_folder_names = [Path(f).name for f in data["empty_folders"]]
        self.assertNotIn(
            "folder_with_special",
            empty_folder_names,
            "Folder with special files should not be marked as empty",
        )

        # Folder should still exist
        self.assertTrue(folder_with_special.exists())

        # Clean up
        broken_symlink.unlink()
        folder_with_special.rmdir()

    def test_errors_dont_count_toward_batch_limit(self):
        """Test that errors don't count toward batch_size, ensuring re-entrancy"""
        import unittest.mock

        # First, clean up existing empty folders from setUp
        client.post("/api/v1/cleanup/empty-folders?dry_run=false")

        # Create 5 empty folders
        folders = []
        for i in range(1, 6):
            folder_path = self.test_path / f"error_batch_test{i}"
            folder_path.mkdir()
            folders.append(folder_path)

        # Track which folders were attempted and which succeeded
        attempted_folders = []
        successful_deletions = []
        failed_folders = []

        original_rmdir = Path.rmdir

        def mock_rmdir(self):
            folder_path_str = str(self.resolve())
            attempted_folders.append(folder_path_str)
            # Fail on the first folder attempted (to guarantee it's in the batch)
            # This ensures the error occurs early enough to test the behavior
            if len(attempted_folders) == 1:
                failed_folders.append(folder_path_str)
                raise OSError("Permission denied")
            # Otherwise, call the original
            result = original_rmdir(self)
            successful_deletions.append(folder_path_str)
            return result

        # Run cleanup with batch_size=3, with one folder failing
        with unittest.mock.patch.object(Path, "rmdir", mock_rmdir):
            response = client.post(
                "/api/v1/cleanup/empty-folders?dry_run=false&batch_size=3"
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()

        # Should have deleted exactly 3 folders (the error doesn't count)
        # The first folder will error, but we should still process other
        # folders to reach batch_size=3 successful deletions
        self.assertEqual(
            data["empty_folders_removed"],
            3,
            "Should delete exactly 3 folders even if one errors. "
            "Errors don't count toward batch limit.",
        )

        # Verify that exactly one folder failed
        self.assertEqual(
            len(failed_folders),
            1,
            "Exactly one folder should have failed",
        )

        # Verify that the failing folder still exists (it had the error)
        failing_folder_path_str = failed_folders[0]
        failing_folder = Path(failing_folder_path_str)
        self.assertTrue(
            failing_folder.exists(),
            "Folder with error should still exist",
        )

        # Verify that exactly 3 other folders were deleted
        deleted_folders = [f for f in folders if not f.exists()]
        self.assertEqual(
            len(deleted_folders),
            3,
            "Exactly 3 folders should be deleted despite the error",
        )

        # Verify the mock was actually called (debugging for CI)
        self.assertGreater(
            len(attempted_folders),
            0,
            "Mock rmdir should have been called at least once",
        )

        # Verify the failing folder was attempted (it should be the first one)
        self.assertIn(
            failing_folder_path_str,
            attempted_folders,
            f"Failing folder {failing_folder_path_str} should have been attempted. "
            f"Attempted: {attempted_folders}",
        )
        self.assertEqual(
            attempted_folders[0],
            failing_folder_path_str,
            "Failing folder should be the first one attempted",
        )

        # Verify the error was recorded in the response
        # Note: The error should be recorded even if it doesn't count toward batch limit
        if data["errors"] == 0:
            # If no errors were recorded, check if the mock was actually called
            # This helps debug CI failures
            self.fail(
                f"Expected at least 1 error, but got 0. "
                f"Attempted folders: {attempted_folders}, "
                f"Successful deletions: {successful_deletions}, "
                f"Response data: {data}"
            )
        self.assertGreater(
            data["errors"],
            0,
            "Error should be recorded in response",
        )

        # Verify error details contain information about the failing folder
        self.assertGreater(
            len(data["error_details"]),
            0,
            "Error details should be included in response",
        )

        # Verify that the failing folder path appears in error details
        error_details_str = " ".join(data["error_details"])
        # The failing folder name should be in the error details
        failing_folder_name = failing_folder.name
        self.assertIn(
            failing_folder_name,
            error_details_str,
            f"Error details should mention the failing folder {failing_folder_name}",
        )

        # Clean up the remaining folder
        failing_folder.rmdir()

    def test_symlink_to_empty_directory_not_marked_as_empty(self):
        """Test that folders containing symlinks to directories are not marked as empty"""
        # First, clean up existing empty folders from setUp
        client.post("/api/v1/cleanup/empty-folders?dry_run=false")

        # Create an empty directory
        empty_target = self.test_path / "empty_target"
        empty_target.mkdir()

        # Create a folder containing a symlink to the empty directory
        folder_with_symlink = self.test_path / "folder_with_dir_symlink"
        folder_with_symlink.mkdir()

        # Create a symlink to the empty directory
        dir_symlink = folder_with_symlink / "link_to_empty"
        dir_symlink.symlink_to(empty_target)

        # Verify symlink exists and points to a directory
        self.assertTrue(dir_symlink.is_symlink())
        self.assertTrue(dir_symlink.is_dir())  # is_dir() follows symlinks

        # Run cleanup - should NOT mark folder_with_symlink as empty
        # even though the symlink points to an empty directory
        response = client.post("/api/v1/cleanup/empty-folders?dry_run=true")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # folder_with_symlink should NOT be in empty folders list
        # The symlink itself is content that makes the folder non-empty
        empty_folder_names = [Path(f).name for f in data["empty_folders"]]
        self.assertNotIn(
            "folder_with_symlink",
            empty_folder_names,
            "Folder with symlink to directory should not be marked as empty",
        )

        # empty_target should be in the empty folders list (it's actually empty)
        self.assertIn(
            "empty_target",
            empty_folder_names,
            "Empty target directory should be marked as empty",
        )

        # Verify folders still exist
        self.assertTrue(folder_with_symlink.exists())
        self.assertTrue(empty_target.exists())

        # Try actual deletion - should delete empty_target but not folder_with_symlink
        response2 = client.post("/api/v1/cleanup/empty-folders?dry_run=false")
        self.assertEqual(response2.status_code, 200)

        # empty_target should be deleted
        self.assertFalse(empty_target.exists())

        # folder_with_symlink should still exist (it's not empty)
        self.assertTrue(folder_with_symlink.exists())

        # Clean up
        dir_symlink.unlink()
        folder_with_symlink.rmdir()

    def test_symlink_to_nested_empty_directory_not_marked_as_empty(self):
        """Test that folders with symlinks to nested empty directories are handled correctly"""
        # First, clean up existing empty folders from setUp
        client.post("/api/v1/cleanup/empty-folders?dry_run=false")

        # Create nested empty directories
        nested_empty = self.test_path / "nested" / "empty"
        nested_empty.mkdir(parents=True)

        # Create a folder containing a symlink to the nested empty directory
        folder_with_symlink = self.test_path / "folder_with_nested_symlink"
        folder_with_symlink.mkdir()

        # Create a symlink to the nested empty directory
        nested_symlink = folder_with_symlink / "link_to_nested"
        nested_symlink.symlink_to(nested_empty)

        # Run cleanup - should NOT mark folder_with_symlink as empty
        response = client.post("/api/v1/cleanup/empty-folders?dry_run=true")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # folder_with_symlink should NOT be in empty folders list
        empty_folder_names = [Path(f).name for f in data["empty_folders"]]
        self.assertNotIn(
            "folder_with_nested_symlink",
            empty_folder_names,
            "Folder with symlink to nested empty directory should not be marked as empty",
        )

        # The nested empty directory should be found (but not deleted yet in dry_run)
        # Check that nested/empty is in the list
        nested_empty_relative = nested_empty.relative_to(self.test_path)
        self.assertTrue(
            any(
                Path(f) == nested_empty_relative for f in data["empty_folders"]
            ),
            "Nested empty directory should be found",
        )

        # Verify folders still exist
        self.assertTrue(folder_with_symlink.exists())
        self.assertTrue(nested_empty.exists())

        # Clean up
        nested_symlink.unlink()
        folder_with_symlink.rmdir()
        # nested/empty will be cleaned up by the next test run's setUp cleanup


if __name__ == "__main__":
    unittest.main()
