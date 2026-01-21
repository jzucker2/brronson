import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestMetricsBehavior(unittest.TestCase):
    """Test the new metrics behavior including zero-out logic"""

    def setUp(self):
        """Set up test directory"""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

        # Set environment variable
        self.original_cleanup_dir = os.environ.get("CLEANUP_DIRECTORY")
        os.environ["CLEANUP_DIRECTORY"] = self.test_dir

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

        if self.original_cleanup_dir is not None:
            os.environ["CLEANUP_DIRECTORY"] = self.original_cleanup_dir
        elif "CLEANUP_DIRECTORY" in os.environ:
            del os.environ["CLEANUP_DIRECTORY"]

    def test_scan_metrics_with_files_found(self):
        """Test scan metrics when files are found"""
        # Create matching files
        (self.test_path / "www.YTS.MX.jpg").touch()
        (self.test_path / ".DS_Store").touch()

        # Perform scan
        response = client.get("/api/v1/cleanup/scan")
        self.assertEqual(response.status_code, 200)

        # Check metrics
        metrics_response = client.get("/metrics")
        metrics_text = metrics_response.text

        # Should have scan metrics
        self.assertIn("brronson_scan_files_found_total", metrics_text)
        self.assertIn("brronson_scan_current_files", metrics_text)
        self.assertIn("brronson_scan_operation_duration_seconds", metrics_text)
        self.assertIn("brronson_scan_directory_size_bytes", metrics_text)

    def test_scan_metrics_with_no_files_found(self):
        """Test scan metrics when no files are found (zero-out behavior)"""
        # Create only non-matching files
        (self.test_path / "normal_file.txt").touch()
        (self.test_path / "another_file.jpg").touch()

        # Perform scan
        response = client.get("/api/v1/cleanup/scan")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["files_found"], 0)

        # Check metrics - should still have metric entries but with zero values
        metrics_response = client.get("/metrics")
        metrics_text = metrics_response.text

        # Should have scan metrics even with zero files
        self.assertIn("brronson_scan_files_found_total", metrics_text)
        self.assertIn("brronson_scan_operation_duration_seconds", metrics_text)

    def test_cleanup_metrics_with_files_found(self):
        """Test cleanup metrics when files are found"""
        # Create matching files
        (self.test_path / "www.YTS.MX.jpg").touch()
        (self.test_path / ".DS_Store").touch()

        # Perform cleanup (dry run)
        response = client.post("/api/v1/cleanup/files?dry_run=true")
        self.assertEqual(response.status_code, 200)

        # Check metrics
        metrics_response = client.get("/metrics")
        metrics_text = metrics_response.text

        # Should have cleanup metrics
        self.assertIn("brronson_cleanup_files_found_total", metrics_text)
        self.assertIn("brronson_cleanup_current_files", metrics_text)
        self.assertIn(
            "brronson_cleanup_operation_duration_seconds", metrics_text
        )
        self.assertIn("brronson_cleanup_directory_size_bytes", metrics_text)

    def test_cleanup_metrics_with_no_files_found(self):
        """Test cleanup metrics when no files are found (zero-out behavior)"""
        # Create only non-matching files
        (self.test_path / "normal_file.txt").touch()
        (self.test_path / "another_file.jpg").touch()

        # Perform cleanup (dry run)
        response = client.post("/api/v1/cleanup/files?dry_run=true")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["files_found"], 0)

        # Check metrics - should still have metric entries but with zero values
        metrics_response = client.get("/metrics")
        metrics_text = metrics_response.text

        # Should have cleanup metrics even with zero files
        self.assertIn("brronson_cleanup_files_found_total", metrics_text)
        self.assertIn("brronson_cleanup_current_files", metrics_text)
        self.assertIn(
            "brronson_cleanup_operation_duration_seconds", metrics_text
        )

    def test_cleanup_metrics_with_actual_removal(self):
        """Test cleanup metrics when files are actually removed"""
        # Create matching files
        (self.test_path / "www.YTS.MX.jpg").touch()
        (self.test_path / ".DS_Store").touch()

        # Perform cleanup (actual removal)
        response = client.post("/api/v1/cleanup/files?dry_run=false")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["files_removed"], 2)

        # Check metrics
        metrics_response = client.get("/metrics")
        metrics_text = metrics_response.text

        # Should have removal metrics
        self.assertIn("brronson_cleanup_files_removed_total", metrics_text)

    def test_metrics_operation_type_differentiation(self):
        """Test that scan and cleanup operations record different metrics"""
        # Create matching files
        (self.test_path / "www.YTS.MX.jpg").touch()

        # Perform scan
        client.get("/api/v1/cleanup/scan")

        # Perform cleanup
        client.post("/api/v1/cleanup/files?dry_run=true")

        # Check metrics
        metrics_response = client.get("/metrics")
        metrics_text = metrics_response.text

        # Should have both scan and cleanup metrics
        self.assertIn("brronson_scan_files_found_total", metrics_text)
        self.assertIn("brronson_scan_current_files", metrics_text)
        self.assertIn("brronson_cleanup_files_found_total", metrics_text)
        self.assertIn("brronson_cleanup_current_files", metrics_text)
        self.assertIn("brronson_scan_operation_duration_seconds", metrics_text)
        self.assertIn(
            "brronson_cleanup_operation_duration_seconds", metrics_text
        )

    def test_error_metrics(self):
        """Test error metrics are recorded properly"""
        # Try to access nonexistent directory
        os.environ["CLEANUP_DIRECTORY"] = "/nonexistent/directory"

        # This should fail and record error metrics
        response = client.get("/api/v1/cleanup/scan")
        self.assertEqual(response.status_code, 400)

        # Check metrics
        metrics_response = client.get("/metrics")
        metrics_text = metrics_response.text

        # Should have error metrics
        self.assertIn("brronson_scan_errors_total", metrics_text)
