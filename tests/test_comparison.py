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


class TestDirectoryComparison(unittest.TestCase):
    """Test the directory comparison functionality"""

    def setUp(self):
        """Set up test directories"""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

        # Create cleanup directory structure
        self.cleanup_dir = self.test_path / "cleanup"
        self.cleanup_dir.mkdir()
        (self.cleanup_dir / "shared_dir1").mkdir()
        (self.cleanup_dir / "shared_dir2").mkdir()
        (self.cleanup_dir / "cleanup_only").mkdir()

        # Create target directory structure
        self.target_dir = self.test_path / "target"
        self.target_dir.mkdir()
        (self.target_dir / "shared_dir1").mkdir()
        (self.target_dir / "shared_dir2").mkdir()
        (self.target_dir / "target_only").mkdir()

        # Set environment variables
        self.original_cleanup_dir = os.environ.get("CLEANUP_DIRECTORY")
        self.original_target_dir = os.environ.get("TARGET_DIRECTORY")
        os.environ["CLEANUP_DIRECTORY"] = str(self.cleanup_dir)
        os.environ["TARGET_DIRECTORY"] = str(self.target_dir)

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

        if self.original_cleanup_dir is not None:
            os.environ["CLEANUP_DIRECTORY"] = self.original_cleanup_dir
        elif "CLEANUP_DIRECTORY" in os.environ:
            del os.environ["CLEANUP_DIRECTORY"]

        if self.original_target_dir is not None:
            os.environ["TARGET_DIRECTORY"] = self.original_target_dir
        elif "TARGET_DIRECTORY" in os.environ:
            del os.environ["TARGET_DIRECTORY"]

    def test_compare_directories_success(self):
        """Test successful directory comparison (default non-verbose)"""
        response = client.get("/api/v1/compare/directories")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check response structure (non-verbose should not include full lists)
        self.assertIn("cleanup_directory", data)
        self.assertIn("target_directory", data)
        self.assertNotIn("cleanup_subdirectories", data)
        self.assertNotIn("target_subdirectories", data)
        self.assertIn("duplicates", data)
        self.assertIn("duplicate_count", data)
        self.assertIn("non_duplicate_count", data)
        self.assertIn("total_cleanup_subdirectories", data)
        self.assertIn("total_target_subdirectories", data)

        # Check expected results
        self.assertEqual(data["duplicate_count"], 2)
        self.assertIn("shared_dir1", data["duplicates"])
        self.assertIn("shared_dir2", data["duplicates"])
        self.assertEqual(data["non_duplicate_count"], 1)  # cleanup_only
        self.assertEqual(data["total_cleanup_subdirectories"], 3)
        self.assertEqual(data["total_target_subdirectories"], 3)

    def test_compare_directories_verbose(self):
        """Test successful directory comparison with verbose flag"""
        response = client.get("/api/v1/compare/directories?verbose=true")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check response structure (verbose should include full lists)
        self.assertIn("cleanup_directory", data)
        self.assertIn("target_directory", data)
        self.assertIn("cleanup_subdirectories", data)
        self.assertIn("target_subdirectories", data)
        self.assertIn("duplicates", data)
        self.assertIn("duplicate_count", data)
        self.assertIn("non_duplicate_count", data)
        self.assertIn("total_cleanup_subdirectories", data)
        self.assertIn("total_target_subdirectories", data)

        # Check expected results
        self.assertEqual(data["duplicate_count"], 2)
        self.assertIn("shared_dir1", data["duplicates"])
        self.assertIn("shared_dir2", data["duplicates"])
        self.assertEqual(data["non_duplicate_count"], 1)  # cleanup_only
        self.assertEqual(data["total_cleanup_subdirectories"], 3)
        self.assertEqual(data["total_target_subdirectories"], 3)
        self.assertIn("cleanup_only", data["cleanup_subdirectories"])
        self.assertIn("target_only", data["target_subdirectories"])

    def test_compare_directories_no_duplicates(self):
        """Test directory comparison with no duplicates"""
        # Remove shared directories
        import shutil

        shutil.rmtree(self.cleanup_dir / "shared_dir1")
        shutil.rmtree(self.cleanup_dir / "shared_dir2")
        shutil.rmtree(self.target_dir / "shared_dir1")
        shutil.rmtree(self.target_dir / "shared_dir2")

        response = client.get("/api/v1/compare/directories")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check response data
        self.assertEqual(data["duplicate_count"], 0)
        self.assertEqual(len(data["duplicates"]), 0)
        self.assertEqual(data["non_duplicate_count"], 1)  # cleanup_only
        self.assertEqual(
            data["total_cleanup_subdirectories"], 1
        )  # cleanup_only
        self.assertEqual(data["total_target_subdirectories"], 1)  # target_only

        # Check metrics - should be set to 0 for no duplicates
        metrics_response = client.get("/metrics")
        metrics_text = metrics_response.text

        # Should have comparison metrics with value 0
        self.assertIn(
            "brronson_comparison_duplicates_found_total", metrics_text
        )
        # The metric should be present but with value 0
        self.assertIn(
            f'brronson_comparison_duplicates_found_total{{cleanup_directory="{normalize_path_for_metrics(self.cleanup_dir)}",target_directory="{normalize_path_for_metrics(self.target_dir)}"}} 0.0',
            metrics_text,
        )

    def test_compare_directories_empty_directories(self):
        """Test directory comparison with empty directories"""
        # Remove all subdirectories
        import shutil

        for subdir in self.cleanup_dir.iterdir():
            if subdir.is_dir():
                shutil.rmtree(subdir)
        for subdir in self.target_dir.iterdir():
            if subdir.is_dir():
                shutil.rmtree(subdir)

        response = client.get("/api/v1/compare/directories")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check response data
        self.assertEqual(data["duplicate_count"], 0)
        self.assertEqual(data["non_duplicate_count"], 0)
        self.assertEqual(data["total_cleanup_subdirectories"], 0)
        self.assertEqual(data["total_target_subdirectories"], 0)

        # Check metrics - should be set to 0 for empty directories
        metrics_response = client.get("/metrics")
        metrics_text = metrics_response.text

        # Should have comparison metrics with value 0
        self.assertIn(
            "brronson_comparison_duplicates_found_total", metrics_text
        )
        # The metric should be present but with value 0
        self.assertIn(
            f'brronson_comparison_duplicates_found_total{{cleanup_directory="{normalize_path_for_metrics(self.cleanup_dir)}",target_directory="{normalize_path_for_metrics(self.target_dir)}"}} 0.0',
            metrics_text,
        )

    def test_compare_directories_nonexistent_cleanup(self):
        """Test directory comparison with nonexistent cleanup directory"""
        os.environ["CLEANUP_DIRECTORY"] = "/nonexistent/cleanup"

        response = client.get("/api/v1/compare/directories")
        self.assertEqual(response.status_code, 404)

    def test_compare_directories_nonexistent_target(self):
        """Test directory comparison with nonexistent target directory"""
        os.environ["TARGET_DIRECTORY"] = "/nonexistent/target"

        response = client.get("/api/v1/compare/directories")
        self.assertEqual(response.status_code, 404)

    def test_compare_directories_metrics(self):
        """Test that directory comparison records metrics"""
        response = client.get("/api/v1/compare/directories")
        self.assertEqual(response.status_code, 200)

        # Check metrics
        metrics_response = client.get("/metrics")
        metrics_text = metrics_response.text

        # Should have comparison metrics
        self.assertIn(
            "brronson_comparison_duplicates_found_total", metrics_text
        )
        self.assertIn(
            "brronson_comparison_non_duplicates_found_total", metrics_text
        )
        self.assertIn(
            "brronson_comparison_operation_duration_seconds", metrics_text
        )
        # Should NOT have subdirectory metrics for comparison operations
        # (only duplicates and non-duplicates are counted, not all subdirectories)

        # Check specific metric values
        cleanup_path_resolved = normalize_path_for_metrics(self.cleanup_dir)
        target_path_resolved = normalize_path_for_metrics(self.target_dir)

        # Check duplicates metric (should be 2: shared_dir1, shared_dir2)
        assert_metric_with_labels(
            metrics_text,
            "brronson_comparison_duplicates_found_total",
            {
                "cleanup_directory": cleanup_path_resolved,
                "target_directory": target_path_resolved,
            },
            "2.0",
        )

        # Check non-duplicates metric (should be 1: cleanup_only)
        assert_metric_with_labels(
            metrics_text,
            "brronson_comparison_non_duplicates_found_total",
            {
                "cleanup_directory": cleanup_path_resolved,
                "target_directory": target_path_resolved,
            },
            "1.0",
        )

    def test_compare_directories_with_files(self):
        """Test that directory comparison
        only looks at directories, not files"""
        # Add some files to the directories
        (self.cleanup_dir / "test_file.txt").touch()
        (self.target_dir / "test_file.txt").touch()
        (self.cleanup_dir / "another_file.jpg").touch()

        # Test with verbose flag to get the full lists
        response = client.get("/api/v1/compare/directories?verbose=true")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Files should not be included in subdirectories
        self.assertNotIn("test_file.txt", data["cleanup_subdirectories"])
        self.assertNotIn("test_file.txt", data["target_subdirectories"])
        another_file = "another_file.jpg"
        cleanup_subdirs = data["cleanup_subdirectories"]
        self.assertNotIn(another_file, cleanup_subdirs)
