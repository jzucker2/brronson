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


if __name__ == "__main__":
    unittest.main()
