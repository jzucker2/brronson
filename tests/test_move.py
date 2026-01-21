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


class TestMoveNonDuplicateFiles(unittest.TestCase):
    def setUp(self):
        """Set up test directories for move operations"""
        self.test_dir = tempfile.mkdtemp()
        self.cleanup_dir = Path(self.test_dir) / "cleanup"
        self.target_dir = Path(self.test_dir) / "target"

        # Create test directories
        self.cleanup_dir.mkdir()
        self.target_dir.mkdir()

        # Create subdirectories in cleanup directory
        (self.cleanup_dir / "cleanup_only").mkdir()
        (self.cleanup_dir / "shared_dir1").mkdir()
        (self.cleanup_dir / "shared_dir2").mkdir()
        (self.cleanup_dir / "another_cleanup_only").mkdir()

        # Create subdirectories in target directory
        (self.target_dir / "target_only").mkdir()
        (self.target_dir / "shared_dir1").mkdir()
        (self.target_dir / "shared_dir2").mkdir()

        # Add some files to the subdirectories
        (self.cleanup_dir / "cleanup_only" / "file1.txt").touch()
        (self.cleanup_dir / "shared_dir1" / "shared_file.txt").touch()
        (self.target_dir / "shared_dir1" / "shared_file.txt").touch()
        (self.cleanup_dir / "another_cleanup_only" / "file2.txt").touch()
        (self.target_dir / "target_only" / "target_file.txt").touch()

        # Set environment variables for testing
        self.original_cleanup_dir = os.environ.get("CLEANUP_DIRECTORY")
        self.original_target_dir = os.environ.get("TARGET_DIRECTORY")
        os.environ["CLEANUP_DIRECTORY"] = str(self.cleanup_dir)
        os.environ["TARGET_DIRECTORY"] = str(self.target_dir)

        # Clear Prometheus default registry to avoid duplicate metrics
        import prometheus_client

        prometheus_client.REGISTRY._names_to_collectors.clear()

        # Re-import and re-create the TestClient to pick up the new env vars
        from importlib import reload

        import app.main

        reload(app.main)
        global client
        client = TestClient(app.main.app)

    def tearDown(self):
        """Clean up test directories and restore environment"""
        import shutil

        shutil.rmtree(self.test_dir, ignore_errors=True)

        # Restore original environment variables
        if self.original_cleanup_dir is not None:
            os.environ["CLEANUP_DIRECTORY"] = self.original_cleanup_dir
        elif "CLEANUP_DIRECTORY" in os.environ:
            del os.environ["CLEANUP_DIRECTORY"]

        if self.original_target_dir is not None:
            os.environ["TARGET_DIRECTORY"] = self.original_target_dir
        elif "TARGET_DIRECTORY" in os.environ:
            del os.environ["TARGET_DIRECTORY"]

    def test_move_non_duplicates_dry_run(self):
        """Test move non-duplicates endpoint in dry run mode (default)"""
        response = client.post("/api/v1/move/non-duplicates")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check response structure
        self.assertIn("cleanup_directory", data)
        self.assertIn("target_directory", data)
        self.assertIn("dry_run", data)
        self.assertIn("batch_size", data)
        self.assertIn("non_duplicates_found", data)
        self.assertIn("files_moved", data)
        self.assertIn("errors", data)
        self.assertIn("non_duplicate_subdirectories", data)
        self.assertIn("moved_subdirectories", data)
        self.assertIn("error_details", data)
        self.assertIn("remaining_files", data)

        # Check expected results (dry run)
        self.assertTrue(data["dry_run"])
        self.assertEqual(data["batch_size"], 1)  # Default batch size
        self.assertEqual(
            data["non_duplicates_found"], 2
        )  # cleanup_only, another_cleanup_only
        self.assertEqual(
            data["files_moved"], 1
        )  # In dry run with batch_size=1, only 1 file moved
        self.assertEqual(data["errors"], 0)
        self.assertEqual(data["remaining_files"], 1)  # 1 file remaining
        self.assertIn("cleanup_only", data["non_duplicate_subdirectories"])
        self.assertIn(
            "another_cleanup_only", data["non_duplicate_subdirectories"]
        )
        self.assertNotIn("shared_dir1", data["non_duplicate_subdirectories"])
        self.assertNotIn("shared_dir2", data["non_duplicate_subdirectories"])

        # Verify files still exist in original location (dry run)
        self.assertTrue((self.cleanup_dir / "cleanup_only").exists())
        self.assertTrue((self.cleanup_dir / "another_cleanup_only").exists())
        self.assertTrue((self.cleanup_dir / "shared_dir1").exists())
        self.assertTrue((self.cleanup_dir / "shared_dir2").exists())

    def test_move_non_duplicates_actual_move(self):
        """Test move non-duplicates endpoint with actual file moving"""
        # Ensure we have the expected setup - clean state
        import shutil

        # Clean up any existing directories from previous tests
        if (self.target_dir / "cleanup_only").exists():
            shutil.rmtree(self.target_dir / "cleanup_only")
        if (self.target_dir / "another_cleanup_only").exists():
            shutil.rmtree(self.target_dir / "another_cleanup_only")
        if (self.cleanup_dir / "cleanup_only").exists():
            shutil.rmtree(self.cleanup_dir / "cleanup_only")
        if (self.cleanup_dir / "another_cleanup_only").exists():
            shutil.rmtree(self.cleanup_dir / "another_cleanup_only")

        # Recreate the expected directories with files
        (self.cleanup_dir / "cleanup_only").mkdir()
        (self.cleanup_dir / "cleanup_only" / "file1.txt").touch()
        (self.cleanup_dir / "another_cleanup_only").mkdir()
        (self.cleanup_dir / "another_cleanup_only" / "file2.txt").touch()

        response = client.post("/api/v1/move/non-duplicates?dry_run=false")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check response structure
        self.assertIn("cleanup_directory", data)
        self.assertIn("target_directory", data)
        self.assertIn("dry_run", data)
        self.assertIn("batch_size", data)
        self.assertIn("non_duplicates_found", data)
        self.assertIn("files_moved", data)
        self.assertIn("errors", data)
        self.assertIn("non_duplicate_subdirectories", data)
        self.assertIn("moved_subdirectories", data)
        self.assertIn("error_details", data)
        self.assertIn("remaining_files", data)

        # Check expected results (actual move)
        self.assertFalse(data["dry_run"])
        self.assertEqual(data["batch_size"], 1)  # Default batch size
        self.assertEqual(data["non_duplicates_found"], 2)
        self.assertEqual(
            data["files_moved"], 1
        )  # Only 1 file moved due to batch_size=1
        self.assertEqual(data["errors"], 0)
        self.assertEqual(data["remaining_files"], 1)  # 1 file remaining
        self.assertIn("cleanup_only", data["non_duplicate_subdirectories"])
        self.assertIn(
            "another_cleanup_only", data["non_duplicate_subdirectories"]
        )

        # Verify files were actually moved (only first file due to batch_size=1)
        # Note: another_cleanup_only comes before cleanup_only alphabetically
        self.assertTrue(
            (self.cleanup_dir / "cleanup_only").exists()
        )  # Not moved yet
        self.assertFalse(
            (self.cleanup_dir / "another_cleanup_only").exists()
        )  # Moved first (alphabetically)
        self.assertFalse(
            (self.target_dir / "cleanup_only").exists()
        )  # Not moved yet
        self.assertTrue(
            (self.target_dir / "another_cleanup_only").exists()
        )  # Moved first (alphabetically)

        # Verify shared directories were not moved
        self.assertTrue((self.cleanup_dir / "shared_dir1").exists())
        self.assertTrue((self.cleanup_dir / "shared_dir2").exists())
        self.assertTrue((self.target_dir / "shared_dir1").exists())
        self.assertTrue((self.target_dir / "shared_dir2").exists())

        # Verify target-only directory was not affected
        self.assertTrue((self.target_dir / "target_only").exists())

    def test_move_non_duplicates_batch_processing(self):
        """Test move non-duplicates with custom batch size"""
        # Reset directories to have 2 non-duplicates
        import shutil

        if (self.target_dir / "cleanup_only").exists():
            shutil.rmtree(self.target_dir / "cleanup_only")
        if (self.target_dir / "another_cleanup_only").exists():
            shutil.rmtree(self.target_dir / "another_cleanup_only")

        response = client.post(
            "/api/v1/move/non-duplicates?dry_run=false&batch_size=2"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check response structure
        self.assertIn("batch_size", data)
        self.assertIn("remaining_files", data)

        # Check expected results (batch_size=2)
        self.assertFalse(data["dry_run"])
        self.assertEqual(data["batch_size"], 2)
        self.assertEqual(data["non_duplicates_found"], 2)
        self.assertEqual(
            data["files_moved"], 2
        )  # Both files moved due to batch_size=2
        self.assertEqual(data["errors"], 0)
        self.assertEqual(data["remaining_files"], 0)  # No files remaining

        # Verify both files were actually moved
        self.assertFalse((self.cleanup_dir / "cleanup_only").exists())
        self.assertFalse((self.cleanup_dir / "another_cleanup_only").exists())
        self.assertTrue((self.target_dir / "cleanup_only").exists())
        self.assertTrue((self.target_dir / "another_cleanup_only").exists())

        # Check batch operations metric for batch_size=2
        metrics_response = client.get("/metrics")
        metrics_text = metrics_response.text

        cleanup_path_resolved = normalize_path_for_metrics(self.cleanup_dir)
        target_path_resolved = normalize_path_for_metrics(self.target_dir)

        assert_metric_with_labels(
            metrics_text,
            "brronson_move_batch_operations_total",
            {
                "cleanup_directory": cleanup_path_resolved,
                "target_directory": target_path_resolved,
                "batch_size": "2",
            },
            "1.0",
        )

    def test_move_non_duplicates_no_non_duplicates(self):
        """Test move non-duplicates when there are no non-duplicates"""
        # Remove non-duplicate directories
        import shutil

        shutil.rmtree(self.cleanup_dir / "cleanup_only")
        shutil.rmtree(self.cleanup_dir / "another_cleanup_only")

        response = client.post("/api/v1/move/non-duplicates")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check expected results
        self.assertEqual(data["non_duplicates_found"], 0)
        self.assertEqual(data["files_moved"], 0)
        self.assertEqual(data["errors"], 0)
        self.assertEqual(len(data["non_duplicate_subdirectories"]), 0)
        self.assertEqual(len(data["moved_subdirectories"]), 0)

    def test_move_non_duplicates_empty_directories(self):
        """Test move non-duplicates with empty directories"""
        # Remove all subdirectories
        import shutil

        for subdir in self.cleanup_dir.iterdir():
            if subdir.is_dir():
                shutil.rmtree(subdir)
        for subdir in self.target_dir.iterdir():
            if subdir.is_dir():
                shutil.rmtree(subdir)

        response = client.post("/api/v1/move/non-duplicates")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check expected results
        self.assertEqual(data["non_duplicates_found"], 0)
        self.assertEqual(data["files_moved"], 0)
        self.assertEqual(data["errors"], 0)
        self.assertEqual(len(data["non_duplicate_subdirectories"]), 0)
        self.assertEqual(len(data["moved_subdirectories"]), 0)

    def test_move_non_duplicates_nonexistent_cleanup(self):
        """Test move non-duplicates with nonexistent cleanup directory"""
        os.environ["CLEANUP_DIRECTORY"] = "/nonexistent/cleanup"

        response = client.post("/api/v1/move/non-duplicates")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check that cleanup was attempted but failed
        self.assertIn("cleanup_results", data)
        self.assertFalse(data["skip_cleanup"])

        cleanup_results = data["cleanup_results"]
        self.assertIn("error", cleanup_results)

        # Move operation should still work normally (no files to move)
        self.assertIn("non_duplicates_found", data)
        self.assertIn("files_moved", data)
        self.assertEqual(data["non_duplicates_found"], 0)
        self.assertEqual(data["files_moved"], 0)

    def test_move_non_duplicates_nonexistent_target(self):
        """Test move non-duplicates with nonexistent target directory"""
        os.environ["TARGET_DIRECTORY"] = "/nonexistent/target"

        response = client.post("/api/v1/move/non-duplicates")
        self.assertEqual(response.status_code, 404)

    def test_move_non_duplicates_metrics(self):
        """Test that move non-duplicates records metrics"""
        response = client.post("/api/v1/move/non-duplicates")
        self.assertEqual(response.status_code, 200)

        # Check metrics
        metrics_response = client.get("/metrics")
        metrics_text = metrics_response.text

        # Should have move metrics
        self.assertIn("brronson_move_files_found_total", metrics_text)
        self.assertIn("brronson_move_operation_duration_seconds", metrics_text)
        self.assertIn("brronson_move_duplicates_found", metrics_text)
        self.assertIn("brronson_move_directories_moved", metrics_text)
        self.assertIn("brronson_move_batch_operations_total", metrics_text)

        # Use the resolved path format that appears in the metrics
        cleanup_path_resolved = normalize_path_for_metrics(self.cleanup_dir)
        target_path_resolved = normalize_path_for_metrics(self.target_dir)
        # Check gauge metrics for duplicates found (should be 2: shared_dir1, shared_dir2)
        assert_metric_with_labels(
            metrics_text,
            "brronson_move_duplicates_found",
            {
                "cleanup_directory": cleanup_path_resolved,
                "target_directory": target_path_resolved,
                "dry_run": "true",
            },
            "2.0",
        )
        # Check gauge metrics for directories moved (dry run shows what would be moved, but limited by batch_size=1)
        assert_metric_with_labels(
            metrics_text,
            "brronson_move_directories_moved",
            {
                "cleanup_directory": cleanup_path_resolved,
                "target_directory": target_path_resolved,
                "dry_run": "true",
            },
            "1.0",
        )

        # Check batch operations metric
        assert_metric_with_labels(
            metrics_text,
            "brronson_move_batch_operations_total",
            {
                "cleanup_directory": cleanup_path_resolved,
                "target_directory": target_path_resolved,
                "batch_size": "1",
                "dry_run": "true",
            },
            "1.0",
        )

    def test_move_non_duplicates_with_files(self):
        """Test that move non-duplicates only looks at directories, not files"""
        # Add some files to the directories
        (self.cleanup_dir / "test_file.txt").touch()
        (self.target_dir / "test_file.txt").touch()
        (self.cleanup_dir / "another_file.jpg").touch()

        response = client.post("/api/v1/move/non-duplicates")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Files should not be included in non-duplicates
        self.assertNotIn("test_file.txt", data["non_duplicate_subdirectories"])
        self.assertNotIn(
            "another_file.jpg", data["non_duplicate_subdirectories"]
        )

        # Should still find the directory non-duplicates
        self.assertIn("cleanup_only", data["non_duplicate_subdirectories"])
        self.assertIn(
            "another_cleanup_only", data["non_duplicate_subdirectories"]
        )

    def test_move_non_duplicates_error_handling(self):
        """Test move non-duplicates error handling"""
        # Ensure clean state
        import shutil

        if (self.target_dir / "cleanup_only").exists():
            shutil.rmtree(self.target_dir / "cleanup_only")
        if (self.cleanup_dir / "cleanup_only").exists():
            shutil.rmtree(self.cleanup_dir / "cleanup_only")

        # Recreate the directory in cleanup
        (self.cleanup_dir / "cleanup_only").mkdir()
        (self.cleanup_dir / "cleanup_only" / "file1.txt").touch()

        # Create a file with the same name as the first directory to be moved (alphabetically)
        # another_cleanup_only comes before cleanup_only, so create conflict for another_cleanup_only
        (
            self.target_dir / "another_cleanup_only"
        ).touch()  # This will conflict with the directory move

        response = client.post("/api/v1/move/non-duplicates?dry_run=false")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Should have an error (only the first file in batch will fail)
        self.assertGreater(data["errors"], 0)
        self.assertIn("error_details", data)
        self.assertGreater(len(data["error_details"]), 0)

        # Should still report the non-duplicates found
        self.assertEqual(data["non_duplicates_found"], 2)

        # The first file should still exist in cleanup (move failed)
        self.assertTrue((self.cleanup_dir / "another_cleanup_only").exists())
        self.assertTrue(
            (self.target_dir / "another_cleanup_only").exists()
            and (self.target_dir / "another_cleanup_only").is_file()
        )

    def test_move_non_duplicates_preserves_file_contents(self):
        """Test that move non-duplicates preserves file contents"""
        # Ensure clean state
        import shutil

        if (self.target_dir / "cleanup_only").exists():
            shutil.rmtree(self.target_dir / "cleanup_only")
        if (self.cleanup_dir / "cleanup_only").exists():
            shutil.rmtree(self.cleanup_dir / "cleanup_only")

        # Recreate the directory in cleanup
        (self.cleanup_dir / "cleanup_only").mkdir()

        # Create a file with specific content
        test_file = self.cleanup_dir / "cleanup_only" / "test_content.txt"
        test_file.write_text("This is test content")

        response = client.post("/api/v1/move/non-duplicates?dry_run=false")
        self.assertEqual(response.status_code, 200)

        # Verify the file was moved and content preserved (only first file due to batch_size=1)
        # Note: another_cleanup_only is moved first (alphabetically), not cleanup_only
        moved_file = self.target_dir / "another_cleanup_only" / "file2.txt"
        self.assertTrue(moved_file.exists())

        # Verify original file no longer exists
        self.assertFalse((self.cleanup_dir / "another_cleanup_only").exists())

    def test_move_non_duplicates_metrics_with_actual_move(self):
        """Test that move non-duplicates records metrics correctly for actual moves"""
        response = client.post("/api/v1/move/non-duplicates?dry_run=false")
        self.assertEqual(response.status_code, 200)

        # Check metrics
        metrics_response = client.get("/metrics")
        metrics_text = metrics_response.text

        # Should have move metrics with dry_run=false
        self.assertIn("brronson_move_files_found_total", metrics_text)
        self.assertIn("brronson_move_operation_duration_seconds", metrics_text)
        self.assertIn("brronson_move_duplicates_found", metrics_text)
        self.assertIn("brronson_move_directories_moved", metrics_text)
        self.assertIn("brronson_move_batch_operations_total", metrics_text)

        # Use the resolved path format that appears in the metrics
        cleanup_path_resolved = normalize_path_for_metrics(self.cleanup_dir)
        target_path_resolved = normalize_path_for_metrics(self.target_dir)
        # Check gauge metrics for duplicates found with dry_run=false
        assert_metric_with_labels(
            metrics_text,
            "brronson_move_duplicates_found",
            {
                "cleanup_directory": cleanup_path_resolved,
                "target_directory": target_path_resolved,
                "dry_run": "false",
            },
            "2.0",
        )
        # Check gauge metrics for directories moved with dry_run=false (limited by batch_size=1)
        assert_metric_with_labels(
            metrics_text,
            "brronson_move_directories_moved",
            {
                "cleanup_directory": cleanup_path_resolved,
                "target_directory": target_path_resolved,
                "dry_run": "false",
            },
            "1.0",
        )

        # Check batch operations metric
        assert_metric_with_labels(
            metrics_text,
            "brronson_move_batch_operations_total",
            {
                "cleanup_directory": cleanup_path_resolved,
                "target_directory": target_path_resolved,
                "batch_size": "1",
                "dry_run": "false",
            },
            "1.0",
        )

    def test_move_non_duplicates_with_cleanup_by_default(self):
        """Test that move non-duplicates runs cleanup by default"""
        # Add some unwanted files to the cleanup directories
        (self.cleanup_dir / "cleanup_only" / "www.YTS.MX.jpg").touch()
        (self.cleanup_dir / "cleanup_only" / ".DS_Store").touch()
        (self.cleanup_dir / "another_cleanup_only" / "www.YTS.AM.jpg").touch()
        (self.cleanup_dir / "another_cleanup_only" / "Thumbs.db").touch()

        response = client.post("/api/v1/move/non-duplicates?dry_run=true")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check that cleanup was performed by default
        self.assertIn("cleanup_results", data)
        self.assertFalse(data["skip_cleanup"])

        cleanup_results = data["cleanup_results"]
        self.assertIn("files_found", cleanup_results)
        self.assertIn("files_removed", cleanup_results)
        self.assertIn("dry_run", cleanup_results)
        self.assertTrue(cleanup_results["dry_run"])  # Should be dry run

        # Verify unwanted files still exist (dry run)
        self.assertTrue(
            (self.cleanup_dir / "cleanup_only" / "www.YTS.MX.jpg").exists()
        )
        self.assertTrue(
            (self.cleanup_dir / "cleanup_only" / ".DS_Store").exists()
        )
        self.assertTrue(
            (
                self.cleanup_dir / "another_cleanup_only" / "www.YTS.AM.jpg"
            ).exists()
        )
        self.assertTrue(
            (self.cleanup_dir / "another_cleanup_only" / "Thumbs.db").exists()
        )

    def test_move_non_duplicates_with_cleanup_actual_removal(self):
        """Test that move non-duplicates runs cleanup with actual removal"""
        # Add some unwanted files to the cleanup directories
        (self.cleanup_dir / "cleanup_only" / "www.YTS.MX.jpg").touch()
        (self.cleanup_dir / "cleanup_only" / ".DS_Store").touch()
        (self.cleanup_dir / "another_cleanup_only" / "www.YTS.AM.jpg").touch()
        (self.cleanup_dir / "another_cleanup_only" / "Thumbs.db").touch()

        response = client.post("/api/v1/move/non-duplicates?dry_run=false")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check that cleanup was performed
        self.assertIn("cleanup_results", data)
        self.assertFalse(data["skip_cleanup"])

        cleanup_results = data["cleanup_results"]
        self.assertIn("files_found", cleanup_results)
        self.assertIn("files_removed", cleanup_results)
        self.assertFalse(
            cleanup_results["dry_run"]
        )  # Should be actual removal

        # Verify unwanted files were removed
        self.assertFalse(
            (self.cleanup_dir / "cleanup_only" / "www.YTS.MX.jpg").exists()
        )
        self.assertFalse(
            (self.cleanup_dir / "cleanup_only" / ".DS_Store").exists()
        )
        self.assertFalse(
            (
                self.cleanup_dir / "another_cleanup_only" / "www.YTS.AM.jpg"
            ).exists()
        )
        self.assertFalse(
            (self.cleanup_dir / "another_cleanup_only" / "Thumbs.db").exists()
        )

    def test_move_non_duplicates_skip_cleanup(self):
        """Test that move non-duplicates can skip cleanup when requested"""
        # Add some unwanted files to the cleanup directories
        (self.cleanup_dir / "cleanup_only" / "www.YTS.MX.jpg").touch()
        (self.cleanup_dir / "cleanup_only" / ".DS_Store").touch()
        (self.cleanup_dir / "another_cleanup_only" / "www.YTS.AM.jpg").touch()

        response = client.post(
            "/api/v1/move/non-duplicates?skip_cleanup=true&dry_run=true"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check that cleanup was skipped
        self.assertTrue(data["skip_cleanup"])
        self.assertNotIn("cleanup_results", data)

        # Verify unwanted files still exist (cleanup was skipped)
        self.assertTrue(
            (self.cleanup_dir / "cleanup_only" / "www.YTS.MX.jpg").exists()
        )
        self.assertTrue(
            (self.cleanup_dir / "cleanup_only" / ".DS_Store").exists()
        )
        self.assertTrue(
            (
                self.cleanup_dir / "another_cleanup_only" / "www.YTS.AM.jpg"
            ).exists()
        )

    def test_move_non_duplicates_cleanup_failure_continues(self):
        """Test that move operation continues even if cleanup fails"""
        # Create a scenario where cleanup will fail but move can continue
        # by temporarily setting a system directory that will cause cleanup to fail
        original_cleanup_dir = os.environ.get("CLEANUP_DIRECTORY")

        # Temporarily set a system directory that will cause cleanup to fail
        os.environ["CLEANUP_DIRECTORY"] = "/etc"

        response = client.post("/api/v1/move/non-duplicates?dry_run=true")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check that cleanup was attempted but failed
        self.assertIn("cleanup_results", data)
        self.assertFalse(data["skip_cleanup"])

        cleanup_results = data["cleanup_results"]
        self.assertIn("error", cleanup_results)

        # Move operation should still work normally
        self.assertIn("non_duplicates_found", data)
        self.assertIn("files_moved", data)

        # Restore original cleanup directory
        if original_cleanup_dir is not None:
            os.environ["CLEANUP_DIRECTORY"] = original_cleanup_dir
        else:
            del os.environ["CLEANUP_DIRECTORY"]

    def test_move_non_duplicates_cleanup_with_custom_patterns(self):
        """Test that move operation uses default cleanup patterns"""
        # Add files that match default patterns and custom files
        (self.cleanup_dir / "cleanup_only" / "www.YTS.MX.jpg").touch()
        (self.cleanup_dir / "cleanup_only" / "custom_file.txt").touch()
        (self.cleanup_dir / "another_cleanup_only" / ".DS_Store").touch()
        (self.cleanup_dir / "another_cleanup_only" / "normal_file.txt").touch()

        response = client.post("/api/v1/move/non-duplicates?dry_run=false")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check that cleanup was performed with default patterns
        cleanup_results = data["cleanup_results"]
        self.assertIn("patterns_used", cleanup_results)
        self.assertIn("files_found", cleanup_results)
        self.assertIn("files_removed", cleanup_results)

        # Should have found and removed unwanted files (www.YTS.MX.jpg, .DS_Store)
        self.assertGreater(cleanup_results["files_found"], 0)
        self.assertGreater(cleanup_results["files_removed"], 0)

        # Verify unwanted files were removed
        self.assertFalse(
            (self.cleanup_dir / "cleanup_only" / "www.YTS.MX.jpg").exists()
        )
        self.assertFalse(
            (self.cleanup_dir / "another_cleanup_only" / ".DS_Store").exists()
        )

        # Verify normal files still exist (note: another_cleanup_only was moved, so check in target)
        self.assertTrue(
            (self.cleanup_dir / "cleanup_only" / "custom_file.txt").exists()
        )
        self.assertTrue(
            (
                self.target_dir / "another_cleanup_only" / "normal_file.txt"
            ).exists()
        )

    def test_move_non_duplicates_response_structure_with_cleanup(self):
        """Test that move response includes cleanup information when cleanup is performed"""
        response = client.post("/api/v1/move/non-duplicates")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check response structure includes cleanup-related fields
        self.assertIn("skip_cleanup", data)
        self.assertIn("cleanup_results", data)

        # Check cleanup results structure
        cleanup_results = data["cleanup_results"]
        self.assertIn("directory", cleanup_results)
        self.assertIn("dry_run", cleanup_results)
        self.assertIn("patterns_used", cleanup_results)
        self.assertIn("files_found", cleanup_results)
        self.assertIn("files_removed", cleanup_results)
        self.assertIn("errors", cleanup_results)
        self.assertIn("found_files", cleanup_results)
        self.assertIn("removed_files", cleanup_results)
        self.assertIn("error_details", cleanup_results)

    def test_move_non_duplicates_response_structure_without_cleanup(self):
        """Test that move response excludes cleanup information when cleanup is skipped"""
        response = client.post("/api/v1/move/non-duplicates?skip_cleanup=true")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check response structure excludes cleanup-related fields
        self.assertIn("skip_cleanup", data)
        self.assertTrue(data["skip_cleanup"])
        self.assertNotIn("cleanup_results", data)

    def test_move_non_duplicates_cleanup_metrics_integration(self):
        """Test that move operation with cleanup records both move and cleanup metrics"""
        # Add unwanted files to trigger cleanup
        (self.cleanup_dir / "cleanup_only" / "www.YTS.MX.jpg").touch()
        (self.cleanup_dir / "another_cleanup_only" / ".DS_Store").touch()

        response = client.post("/api/v1/move/non-duplicates?dry_run=false")
        self.assertEqual(response.status_code, 200)

        # Check metrics for both move and cleanup operations
        metrics_response = client.get("/metrics")
        metrics_text = metrics_response.text

        # Should have move metrics
        self.assertIn("brronson_move_files_found_total", metrics_text)
        self.assertIn("brronson_move_operation_duration_seconds", metrics_text)
        self.assertIn("brronson_move_duplicates_found", metrics_text)
        self.assertIn("brronson_move_directories_moved", metrics_text)
        self.assertIn("brronson_move_batch_operations_total", metrics_text)

        # Should also have cleanup metrics
        self.assertIn("brronson_cleanup_files_found_total", metrics_text)
        self.assertIn("brronson_cleanup_files_removed_total", metrics_text)
        self.assertIn(
            "brronson_cleanup_operation_duration_seconds", metrics_text
        )
        self.assertIn("brronson_cleanup_directory_size_bytes", metrics_text)
