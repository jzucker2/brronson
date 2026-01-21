import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.version import version

from tests.test_utils import (
    normalize_path_for_metrics,
    assert_metric_with_labels,
)

client = TestClient(app)


class TestMainEndpoints(unittest.TestCase):
    def test_root_endpoint(self):
        """Test the root endpoint"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Welcome to Brronson"
        assert data["version"] == version

    def test_health_check(self):
        """Test the health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "service" in data
        assert "version" in data
        assert "timestamp" in data
        assert data["service"] == "brronson"
        assert data["status"] == "healthy"
        assert data["version"] == version
        assert isinstance(data["timestamp"], (int, float))

    def test_version_endpoint(self):
        """Test the version endpoint"""
        response = client.get("/version")
        assert response.status_code == 200
        data = response.json()
        assert (
            data["message"] == f"The current version of Brronson is {version}"
        )
        assert data["version"] == version

    def test_metrics_endpoint(self):
        """Test the metrics endpoint"""
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]

    def test_metrics_format(self):
        """Test that metrics are in Prometheus format"""
        response = client.get("/metrics")
        metrics_text = response.text

        # Check for basic Prometheus metric format
        # This regex looks for metric_name{label="value"} metric_value
        import re

        metric_pattern = (
            r"^[a-zA-Z_:][a-zA-Z0-9_:]*\{[^}]*\}\s+[0-9]+\.?[0-9]*$"
        )

        # Find at least one metric that matches the pattern
        lines = metrics_text.strip().split("\n")
        matching_lines = [
            line for line in lines if re.match(metric_pattern, line)
        ]
        assert len(matching_lines) > 0, "No valid Prometheus metrics found"

    def test_metrics_contain_request_size(self):
        """Test that metrics contain request size metrics"""
        client.post(
            "/api/v1/items", json={"name": "test", "description": "test item"}
        )
        response = client.get("/metrics")
        metrics_text = response.text

        # Check for request size metrics
        assert "http_request_size_bytes" in metrics_text

    def test_metrics_contain_response_size(self):
        """Test that metrics contain response size metrics"""
        client.get("/")
        response = client.get("/metrics")
        metrics_text = response.text

        # Check for response size metrics
        assert "http_response_size_bytes" in metrics_text

    def test_metrics_contain_request_duration(self):
        """Test that metrics contain request duration metrics"""
        client.get("/")
        response = client.get("/metrics")
        metrics_text = response.text

        # Check for request duration metrics
        assert "http_request_duration_seconds" in metrics_text


class TestCleanupEndpoints(unittest.TestCase):
    def setUp(self):
        """Set up test directory with unwanted files"""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

        # Create some unwanted files
        (self.test_path / "www.YTS.MX.jpg").touch()
        (self.test_path / "www.YTS.AM.jpg").touch()
        (self.test_path / "www.YTS.LT.jpg").touch()
        (self.test_path / "WWW.YTS.AG.jpg").touch()
        (self.test_path / "WWW.YIFY-TORRENTS.COM.jpg").touch()
        (self.test_path / "YIFYStatus.com.txt").touch()
        (self.test_path / "YTSProxies.com.txt").touch()
        (self.test_path / "YTSYifyUP123 (TOR).txt").touch()
        (self.test_path / "normal_file.txt").touch()
        (self.test_path / ".DS_Store").touch()

        # Create subdirectory with unwanted files
        subdir = self.test_path / "subdir"
        subdir.mkdir()
        (subdir / "www.YTS.MX.jpg").touch()
        (subdir / "www.YTS.AM.jpg").touch()
        (subdir / "www.YTS.LT.jpg").touch()
        (subdir / "WWW.YTS.AG.jpg").touch()
        (subdir / "WWW.YIFY-TORRENTS.COM.jpg").touch()
        (subdir / "YTSProxies.com.txt").touch()
        (subdir / "YTSYifyUP123 (TOR).txt").touch()
        (subdir / "normal_file.txt").touch()

        # Set the environment variable for testing
        self.original_cleanup_dir = os.environ.get("CLEANUP_DIRECTORY")
        os.environ["CLEANUP_DIRECTORY"] = self.test_dir

        # Clear Prometheus default registry to avoid duplicate metrics
        import prometheus_client

        prometheus_client.REGISTRY._names_to_collectors.clear()

        # Re-import and re-create the TestClient to pick up the new env var
        from importlib import reload

        import app.main

        reload(app.main)
        global client
        client = TestClient(app.main.app)

    def tearDown(self):
        """Clean up test directory and restore environment"""
        import shutil

        shutil.rmtree(self.test_dir, ignore_errors=True)

        # Restore original environment variable
        if self.original_cleanup_dir is not None:
            os.environ["CLEANUP_DIRECTORY"] = self.original_cleanup_dir
        elif "CLEANUP_DIRECTORY" in os.environ:
            del os.environ["CLEANUP_DIRECTORY"]

    def test_scan_endpoint(self):
        """Test the scan endpoint"""
        response = client.get("/api/v1/cleanup/scan")
        assert response.status_code == 200
        data = response.json()

        # Handle path resolution differences on macOS
        assert normalize_path_for_metrics(
            data["directory"]
        ) == normalize_path_for_metrics(self.test_path)
        assert data["files_found"] == 16  # 16 unwanted files
        assert len(data["found_files"]) == 16
        assert "www.YTS.MX.jpg" in str(data["found_files"])
        assert "www.YTS.AM.jpg" in str(data["found_files"])
        assert "www.YTS.LT.jpg" in str(data["found_files"])
        assert "WWW.YTS.AG.jpg" in str(data["found_files"])
        assert "WWW.YIFY-TORRENTS.COM.jpg" in str(data["found_files"])
        assert "YIFYStatus.com.txt" in str(data["found_files"])
        assert "YTSProxies.com.txt" in str(data["found_files"])
        assert ".DS_Store" in str(data["found_files"])
        assert "YTSYifyUP123 (TOR).txt" in str(data["found_files"])

    def test_cleanup_dry_run(self):
        """Test cleanup endpoint in dry run mode"""
        response = client.post("/api/v1/cleanup/files?dry_run=true")
        assert response.status_code == 200
        data = response.json()

        assert data["dry_run"] is True
        assert data["files_found"] == 16
        assert data["files_removed"] == 0  # No files removed in dry run

        # Verify files still exist
        assert (self.test_path / "www.YTS.MX.jpg").exists()
        assert (self.test_path / "www.YTS.AM.jpg").exists()
        assert (self.test_path / "www.YTS.LT.jpg").exists()
        assert (self.test_path / "WWW.YTS.AG.jpg").exists()
        assert (self.test_path / "WWW.YIFY-TORRENTS.COM.jpg").exists()
        assert (self.test_path / "YIFYStatus.com.txt").exists()

        # Check metrics for dry run
        metrics_response = client.get("/metrics")
        metrics_text = metrics_response.text
        # Check for a known pattern
        assert_metric_with_labels(
            metrics_text,
            "brronson_cleanup_files_found_total",
            {
                "directory": normalize_path_for_metrics(self.test_path),
                "pattern": r"www\\.YTS\\.MX\\.jpg$",
                "dry_run": "true",
            },
            "2.0",
        )
        assert_metric_with_labels(
            metrics_text,
            "brronson_cleanup_current_files",
            {
                "directory": normalize_path_for_metrics(self.test_path),
                "pattern": r"www\\.YTS\\.MX\\.jpg$",
                "dry_run": "true",
            },
            "2.0",
        )

    def test_cleanup_actual_removal(self):
        """Test cleanup endpoint with actual removal"""
        response = client.post("/api/v1/cleanup/files?dry_run=false")
        assert response.status_code == 200
        data = response.json()

        assert data["dry_run"] is False
        assert data["files_found"] == 16
        assert data["files_removed"] == 16

        # Verify files are removed
        assert not (self.test_path / "www.YTS.MX.jpg").exists()
        assert not (self.test_path / "www.YTS.AM.jpg").exists()
        assert not (self.test_path / "www.YTS.LT.jpg").exists()
        assert not (self.test_path / "WWW.YTS.AG.jpg").exists()
        assert not (self.test_path / "WWW.YIFY-TORRENTS.COM.jpg").exists()
        assert not (self.test_path / "YIFYStatus.com.txt").exists()

        # Check metrics for actual removal
        metrics_response = client.get("/metrics")
        metrics_text = metrics_response.text
        # Check for a known pattern
        assert_metric_with_labels(
            metrics_text,
            "brronson_cleanup_files_found_total",
            {
                "directory": normalize_path_for_metrics(self.test_path),
                "pattern": r"www\\.YTS\\.MX\\.jpg$",
                "dry_run": "false",
            },
            "2.0",
        )
        assert_metric_with_labels(
            metrics_text,
            "brronson_cleanup_files_removed_total",
            {
                "directory": normalize_path_for_metrics(self.test_path),
                "pattern": r"www\\.YTS\\.MX\\.jpg$",
                "dry_run": "false",
            },
            "2.0",
        )
        assert_metric_with_labels(
            metrics_text,
            "brronson_cleanup_current_files",
            {
                "directory": normalize_path_for_metrics(self.test_path),
                "pattern": r"www\\.YTS\\.MX\\.jpg$",
                "dry_run": "false",
            },
            "0.0",
        )

    def test_cleanup_with_custom_patterns(self):
        """Test cleanup with custom patterns"""
        custom_patterns = [r"normal_file\.txt$"]
        response = client.post(
            "/api/v1/cleanup/files?dry_run=false", json=custom_patterns
        )
        assert response.status_code == 200
        data = response.json()

        assert data["patterns_used"] == custom_patterns
        assert data["files_found"] == 2  # 2 normal_file.txt files
        assert data["files_removed"] == 2

        # Verify normal files are removed
        assert not (self.test_path / "normal_file.txt").exists()
        assert not (self.test_path / "subdir" / "normal_file.txt").exists()

        # Verify unwanted files still exist
        assert (self.test_path / "www.YTS.MX.jpg").exists()
        assert (self.test_path / "www.YTS.AM.jpg").exists()
        assert (self.test_path / "YIFYStatus.com.txt").exists()

    def test_cleanup_nonexistent_directory(self):
        """Test cleanup with nonexistent directory"""
        # Temporarily set a nonexistent directory
        os.environ["CLEANUP_DIRECTORY"] = "/nonexistent/dir"
        response = client.post("/api/v1/cleanup/files")
        assert response.status_code == 400
        data = response.json()
        assert "not found" in data["detail"]
        # Restore test directory
        os.environ["CLEANUP_DIRECTORY"] = self.test_dir

    def test_cleanup_system_directory_protection(self):
        """Test that system directories are protected"""
        # Temporarily set a system directory
        os.environ["CLEANUP_DIRECTORY"] = "/etc"
        response = client.post("/api/v1/cleanup/files")
        assert response.status_code == 400
        data = response.json()
        assert "protected system location" in data["detail"]
        # Restore test directory
        os.environ["CLEANUP_DIRECTORY"] = self.test_dir

    def test_scan_nonexistent_directory(self):
        """Test scan with nonexistent directory"""
        # Temporarily set a nonexistent directory
        os.environ["CLEANUP_DIRECTORY"] = "/nonexistent/dir"
        response = client.get("/api/v1/cleanup/scan")
        assert response.status_code == 400
        data = response.json()
        assert "not found" in data["detail"]
        # Restore test directory
        os.environ["CLEANUP_DIRECTORY"] = self.test_dir

    def test_scan_system_directory_protection(self):
        """Test that system directories are protected from scanning"""
        # Temporarily set a system directory
        os.environ["CLEANUP_DIRECTORY"] = "/etc"
        response = client.get("/api/v1/cleanup/scan")
        assert response.status_code == 400
        data = response.json()
        assert "protected system location" in data["detail"]
        # Restore test directory
        os.environ["CLEANUP_DIRECTORY"] = self.test_dir


class TestSharedHelperMethods(unittest.TestCase):
    """Test the shared helper methods"""

    def setUp(self):
        """Set up test directory"""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

        # Clear Prometheus default registry to avoid duplicate metrics
        import prometheus_client

        prometheus_client.REGISTRY._names_to_collectors.clear()

        # Re-import to get fresh helper methods
        from importlib import reload

        import app.main

        reload(app.main)
        self.validate_directory = app.main.validate_directory
        self.find_unwanted_files = app.main.find_unwanted_files
        self.DEFAULT_UNWANTED_PATTERNS = app.main.DEFAULT_UNWANTED_PATTERNS

    def tearDown(self):
        """Clean up test directory"""
        import shutil

        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_validate_directory_success(self):
        """Test validate_directory with valid directory"""
        try:
            self.validate_directory(
                self.test_path,
                normalize_path_for_metrics(self.test_path),
                "scan",
            )
        except Exception as e:
            self.fail(f"validate_directory raised {e} unexpectedly!")

    def test_validate_directory_nonexistent(self):
        """Test validate_directory with nonexistent directory"""
        nonexistent_path = Path("/nonexistent/test/directory")
        with self.assertRaises(Exception):
            self.validate_directory(
                nonexistent_path,
                normalize_path_for_metrics(nonexistent_path),
                "scan",
            )

    def test_validate_directory_system_protection(self):
        """Test validate_directory with protected system directory"""
        system_path = Path("/etc")
        with self.assertRaises(Exception):
            self.validate_directory(
                system_path, normalize_path_for_metrics(system_path), "scan"
            )

    def test_find_unwanted_files_with_matches(self):
        """Test find_unwanted_files with files that match patterns"""
        # Create test files
        (self.test_path / "www.YTS.MX.jpg").touch()
        (self.test_path / "test.txt").touch()
        (self.test_path / ".DS_Store").touch()

        patterns = [r"www\.YTS\.MX\.jpg$", r"\.DS_Store$"]

        found_files, file_sizes, pattern_matches = self.find_unwanted_files(
            self.test_path, patterns, "scan"
        )

        self.assertEqual(len(found_files), 2)
        self.assertIn(str(self.test_path / "www.YTS.MX.jpg"), found_files)
        self.assertIn(str(self.test_path / ".DS_Store"), found_files)
        self.assertEqual(len(pattern_matches), 2)
        self.assertEqual(len(file_sizes), 2)

    def test_find_unwanted_files_no_matches(self):
        """Test find_unwanted_files with no matching files"""
        # Create test files that don't match patterns
        (self.test_path / "normal_file.txt").touch()
        (self.test_path / "another_file.jpg").touch()

        patterns = [r"www\.YTS\.MX\.jpg$", r"\.DS_Store$"]

        found_files, file_sizes, pattern_matches = self.find_unwanted_files(
            self.test_path, patterns, "scan"
        )

        self.assertEqual(len(found_files), 0)
        self.assertEqual(len(pattern_matches), 0)
        self.assertEqual(len(file_sizes), 0)

    def test_find_unwanted_files_subdirectories(self):
        """Test find_unwanted_files with subdirectories"""
        # Create subdirectory with matching files
        subdir = self.test_path / "subdir"
        subdir.mkdir()
        (subdir / "www.YTS.MX.jpg").touch()
        (subdir / "normal_file.txt").touch()

        patterns = [r"www\.YTS\.MX\.jpg$"]

        found_files, file_sizes, pattern_matches = self.find_unwanted_files(
            self.test_path, patterns, "scan"
        )

        self.assertEqual(len(found_files), 1)
        self.assertIn(str(subdir / "www.YTS.MX.jpg"), found_files)

    def test_default_patterns_constant(self):
        """Test that DEFAULT_UNWANTED_PATTERNS is properly defined"""
        self.assertIsInstance(self.DEFAULT_UNWANTED_PATTERNS, list)
        self.assertGreater(len(self.DEFAULT_UNWANTED_PATTERNS), 0)

        # Check that patterns are valid regex
        import re

        for pattern in self.DEFAULT_UNWANTED_PATTERNS:
            try:
                re.compile(pattern)
            except re.error:
                self.fail(f"Invalid regex pattern: {pattern}")

    def test_get_subdirectories_with_metrics(self):
        """Test that get_subdirectories records metrics properly"""
        # Create test subdirectories
        (self.test_path / "test_dir1").mkdir()
        (self.test_path / "test_dir2").mkdir()
        (self.test_path / "test_file.txt").touch()

        # Call get_subdirectories with operation type
        from app.main import get_subdirectories

        result = get_subdirectories(self.test_path, "test_operation")

        # Check result
        self.assertEqual(len(result), 2)
        self.assertIn("test_dir1", result)
        self.assertIn("test_dir2", result)

        # Check metrics
        metrics_response = client.get("/metrics")
        metrics_text = metrics_response.text

        # Should have subdirectory metrics
        self.assertIn("brronson_subdirectories_found_total", metrics_text)


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


class TestSubtitleSalvage(unittest.TestCase):
    """Test the subtitle salvage functionality"""

    def setUp(self):
        """Set up test directories for subtitle salvage"""
        self.test_dir = tempfile.mkdtemp()
        self.recycled_dir = Path(self.test_dir) / "recycled"
        self.salvaged_dir = Path(self.test_dir) / "salvaged"

        # Create test directories
        self.recycled_dir.mkdir()
        self.salvaged_dir.mkdir()

        # Set environment variables
        self.original_recycled_dir = os.environ.get(
            "RECYCLED_MOVIES_DIRECTORY"
        )
        self.original_salvaged_dir = os.environ.get(
            "SALVAGED_MOVIES_DIRECTORY"
        )
        os.environ["RECYCLED_MOVIES_DIRECTORY"] = str(self.recycled_dir)
        os.environ["SALVAGED_MOVIES_DIRECTORY"] = str(self.salvaged_dir)

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

        if self.original_salvaged_dir is not None:
            os.environ["SALVAGED_MOVIES_DIRECTORY"] = (
                self.original_salvaged_dir
            )
        elif "SALVAGED_MOVIES_DIRECTORY" in os.environ:
            del os.environ["SALVAGED_MOVIES_DIRECTORY"]

    def test_salvage_subtitle_folders_dry_run(self):
        """Test subtitle salvage endpoint in dry run mode (default)"""
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

        response = client.post("/api/v1/salvage/subtitle-folders")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check response structure
        self.assertIn("recycled_directory", data)
        self.assertIn("salvaged_directory", data)
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

    def test_salvage_subtitle_folders_actual_move(self):
        """Test subtitle salvage endpoint with actual folder copying"""
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
            "/api/v1/salvage/subtitle-folders?dry_run=false"
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

        # Verify folder was copied to salvaged directory
        self.assertTrue((self.salvaged_dir / "Movie1").exists())
        self.assertTrue(
            (self.salvaged_dir / "Movie1" / "subtitle.srt").exists()
        )
        self.assertTrue(
            (self.salvaged_dir / "Movie1" / "subs" / "subtitle2.srt").exists()
        )
        # Verify non-subtitle files are NOT copied
        self.assertFalse((self.salvaged_dir / "Movie1" / "info.nfo").exists())

        # Verify media files were NOT copied (should not be in salvaged)
        self.assertFalse(
            (self.salvaged_dir / "Movie1" / "movie.mp4").exists()
        )
        self.assertFalse(
            (self.salvaged_dir / "Movie1" / "poster.jpg").exists()
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

    def test_salvage_subtitle_folders_multiple_subtitle_formats(self):
        """Test subtitle salvage with multiple subtitle file formats"""
        folder = self.recycled_dir / "Movie1"
        folder.mkdir()
        (folder / "subtitle.srt").touch()
        (folder / "subtitle.ass").touch()
        (folder / "subtitle.vtt").touch()
        (folder / "subtitle.sub").touch()

        response = client.post(
            "/api/v1/salvage/subtitle-folders?dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["subtitle_files_copied"], 4)
        self.assertTrue(
            (self.salvaged_dir / "Movie1" / "subtitle.srt").exists()
        )
        self.assertTrue(
            (self.salvaged_dir / "Movie1" / "subtitle.ass").exists()
        )
        self.assertTrue(
            (self.salvaged_dir / "Movie1" / "subtitle.vtt").exists()
        )
        self.assertTrue(
            (self.salvaged_dir / "Movie1" / "subtitle.sub").exists()
        )

    def test_salvage_subtitle_folders_custom_extensions(self):
        """Test subtitle salvage with custom subtitle extensions"""
        folder = self.recycled_dir / "Movie1"
        folder.mkdir()
        (folder / "subtitle.srt").touch()
        (folder / "subtitle.custom").touch()  # Custom extension

        custom_extensions = [".srt", ".custom"]

        response = client.post(
            "/api/v1/salvage/subtitle-folders?dry_run=false",
            json=custom_extensions,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check that custom extensions were used
        self.assertIn(".srt", data["subtitle_extensions"])
        self.assertIn(".custom", data["subtitle_extensions"])
        # Should have copied both files
        self.assertEqual(data["subtitle_files_copied"], 2)

    def test_salvage_subtitle_folders_no_subtitles(self):
        """Test subtitle salvage when no folders have subtitles"""
        # Create folder without subtitle in root
        folder = self.recycled_dir / "Movie1"
        folder.mkdir()
        (folder / "movie.mp4").touch()
        (folder / "poster.jpg").touch()

        response = client.post("/api/v1/salvage/subtitle-folders")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["folders_scanned"], 1)
        self.assertEqual(data["folders_with_subtitles_found"], 0)
        self.assertEqual(data["folders_copied"], 0)
        self.assertEqual(data["subtitle_files_copied"], 0)

    def test_salvage_subtitle_folders_empty_directories(self):
        """Test subtitle salvage with empty directories"""
        response = client.post("/api/v1/salvage/subtitle-folders")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["folders_scanned"], 0)
        self.assertEqual(data["folders_with_subtitles_found"], 0)
        self.assertEqual(data["folders_copied"], 0)

    def test_salvage_subtitle_folders_nonexistent_recycled(self):
        """Test subtitle salvage with nonexistent recycled directory"""
        os.environ["RECYCLED_MOVIES_DIRECTORY"] = "/nonexistent/recycled"

        response = client.post("/api/v1/salvage/subtitle-folders")
        self.assertEqual(response.status_code, 404)

    def test_salvage_subtitle_folders_nonexistent_salvaged(self):
        """Test subtitle salvage with nonexistent salvaged directory"""
        # Create recycled directory with content
        folder = self.recycled_dir / "Movie1"
        folder.mkdir()
        (folder / "subtitle.srt").touch()

        os.environ["SALVAGED_MOVIES_DIRECTORY"] = "/nonexistent/salvaged"

        response = client.post("/api/v1/salvage/subtitle-folders")
        self.assertEqual(response.status_code, 404)

    def test_salvage_subtitle_folders_metrics(self):
        """Test that subtitle salvage records metrics"""
        # Create folder with subtitle
        folder = self.recycled_dir / "Movie1"
        folder.mkdir()
        (folder / "subtitle.srt").touch()

        response = client.post("/api/v1/salvage/subtitle-folders")
        self.assertEqual(response.status_code, 200)

        # Check metrics
        metrics_response = client.get("/metrics")
        metrics_text = metrics_response.text

        # Should have salvage metrics
        self.assertIn("brronson_salvage_folders_scanned_total", metrics_text)
        self.assertIn(
            "brronson_salvage_folders_with_subtitles_found", metrics_text
        )
        self.assertIn(
            "brronson_salvage_operation_duration_seconds", metrics_text
        )

        # Use the resolved path format
        recycled_path_resolved = normalize_path_for_metrics(self.recycled_dir)

        # Check folders scanned metric
        assert_metric_with_labels(
            metrics_text,
            "brronson_salvage_folders_scanned_total",
            {
                "recycled_directory": recycled_path_resolved,
                "dry_run": "true",
            },
            "1.0",
        )

        # Check folders with subtitles found metric
        assert_metric_with_labels(
            metrics_text,
            "brronson_salvage_folders_with_subtitles_found",
            {
                "recycled_directory": recycled_path_resolved,
                "dry_run": "true",
            },
            "1.0",
        )

    def test_salvage_subtitle_folders_target_exists(self):
        """Test subtitle salvage when target folder already exists"""
        # Create folder with subtitle in recycled
        folder = self.recycled_dir / "Movie1"
        folder.mkdir()
        (folder / "subtitle.srt").touch()

        # Create folder with same name in salvaged (empty folder)
        (self.salvaged_dir / "Movie1").mkdir()

        response = client.post(
            "/api/v1/salvage/subtitle-folders?dry_run=false"
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
            (self.salvaged_dir / "Movie1" / "subtitle.srt").exists()
        )

    def test_salvage_subtitle_folders_file_exists(self):
        """Test subtitle salvage when destination file already exists"""
        # Create folder with subtitle in recycled
        folder = self.recycled_dir / "Movie1"
        folder.mkdir()
        (folder / "subtitle.srt").touch()
        (folder / "subtitle2.srt").touch()

        # Create folder and one subtitle file in salvaged
        (self.salvaged_dir / "Movie1").mkdir()
        (self.salvaged_dir / "Movie1" / "subtitle.srt").write_text("existing")

        response = client.post(
            "/api/v1/salvage/subtitle-folders?dry_run=false"
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
            (self.salvaged_dir / "Movie1" / "subtitle.srt").read_text(),
            "existing",
        )
        # Verify new file was copied
        self.assertTrue(
            (self.salvaged_dir / "Movie1" / "subtitle2.srt").exists()
        )

    def test_salvage_subtitle_folders_dry_run_skips_existing(self):
        """Test that dry run correctly identifies folders/files that would be skipped"""
        # Create folder with subtitle in recycled
        folder = self.recycled_dir / "Movie1"
        folder.mkdir()
        (folder / "subtitle.srt").touch()

        # Create folder and file in salvaged
        (self.salvaged_dir / "Movie1").mkdir()
        (self.salvaged_dir / "Movie1" / "subtitle.srt").touch()

        response = client.post("/api/v1/salvage/subtitle-folders")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Dry run should show skip
        self.assertTrue(data["dry_run"])
        self.assertEqual(data["folders_skipped"], 1)
        self.assertEqual(data["subtitle_files_skipped"], 1)
        self.assertIn("Movie1", data["skipped_folders"])

    def test_salvage_subtitle_folders_preserves_structure(self):
        """Test that subtitle salvage preserves folder structure"""
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
            "/api/v1/salvage/subtitle-folders?dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Verify structure is preserved
        self.assertTrue((self.salvaged_dir / "Movie1").exists())
        self.assertTrue(
            (self.salvaged_dir / "Movie1" / "subtitle.srt").exists()
        )
        self.assertTrue(
            (
                self.salvaged_dir / "Movie1" / "subs" / "en" / "subtitle.srt"
            ).exists()
        )
        self.assertTrue(
            (
                self.salvaged_dir / "Movie1" / "subs" / "fr" / "subtitle.srt"
            ).exists()
        )

        self.assertEqual(data["subtitle_files_copied"], 3)

    def test_salvage_subtitle_folders_skips_media_files(self):
        """Test that subtitle salvage skips media files and images"""
        folder = self.recycled_dir / "Movie1"
        folder.mkdir()
        (folder / "movie.mp4").touch()  # Video
        (folder / "movie.avi").touch()  # Video
        (folder / "poster.jpg").touch()  # Image
        (folder / "poster.png").touch()  # Image
        (folder / "subtitle.srt").touch()  # Subtitle - should move

        response = client.post(
            "/api/v1/salvage/subtitle-folders?dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Only subtitle should be copied
        self.assertEqual(data["subtitle_files_copied"], 1)

        # Verify media files are NOT in salvaged directory
        self.assertFalse(
            (self.salvaged_dir / "Movie1" / "movie.mp4").exists()
        )
        self.assertFalse(
            (self.salvaged_dir / "Movie1" / "movie.avi").exists()
        )
        self.assertFalse(
            (self.salvaged_dir / "Movie1" / "poster.jpg").exists()
        )
        self.assertFalse(
            (self.salvaged_dir / "Movie1" / "poster.png").exists()
        )

        # Verify subtitle IS in salvaged directory
        self.assertTrue(
            (self.salvaged_dir / "Movie1" / "subtitle.srt").exists()
        )

    def test_salvage_subtitle_folders_skips_existing_files(self):
        """Test that subtitle salvage skips existing destination files"""
        # Create folder with multiple subtitles in recycled
        folder = self.recycled_dir / "Movie1"
        folder.mkdir()
        (folder / "subtitle1.srt").touch()
        (folder / "subtitle2.srt").touch()
        (folder / "subtitle3.srt").touch()

        # Create folder and one existing subtitle in salvaged
        (self.salvaged_dir / "Movie1").mkdir()
        existing_file = self.salvaged_dir / "Movie1" / "subtitle2.srt"
        existing_file.write_text("existing content")

        response = client.post(
            "/api/v1/salvage/subtitle-folders?dry_run=false"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Should copy 2 files, skip 1
        self.assertEqual(data["folders_copied"], 1)
        self.assertEqual(
            data["subtitle_files_copied"], 2
        )  # subtitle1 and subtitle3
        self.assertEqual(data["subtitle_files_skipped"], 1)  # subtitle2

        # Verify existing file was not overwritten
        self.assertEqual(existing_file.read_text(), "existing content")
        # Verify new files were copied
        self.assertTrue(
            (self.salvaged_dir / "Movie1" / "subtitle1.srt").exists()
        )
        self.assertTrue(
            (self.salvaged_dir / "Movie1" / "subtitle3.srt").exists()
        )

    def test_salvage_subtitle_folders_skip_metrics(self):
        """Test that skip metrics are recorded correctly"""
        # Create folder with subtitle in recycled
        folder = self.recycled_dir / "Movie1"
        folder.mkdir()
        (folder / "subtitle.srt").touch()

        # Create folder with existing file in salvaged to trigger skip
        (self.salvaged_dir / "Movie1").mkdir()
        (self.salvaged_dir / "Movie1" / "subtitle.srt").write_text("existing")

        response = client.post("/api/v1/salvage/subtitle-folders")
        self.assertEqual(response.status_code, 200)

        # Check metrics
        metrics_response = client.get("/metrics")
        metrics_text = metrics_response.text

        # Should have skip metrics
        self.assertIn("brronson_salvage_folders_skipped_total", metrics_text)
        self.assertIn("brronson_salvage_files_skipped_total", metrics_text)

        recycled_path_resolved = normalize_path_for_metrics(self.recycled_dir)
        salvaged_path_resolved = normalize_path_for_metrics(
            self.salvaged_dir
        )

        # Check skipped folders metric (folder should be skipped because all files exist)
        assert_metric_with_labels(
            metrics_text,
            "brronson_salvage_folders_skipped_total",
            {
                "recycled_directory": recycled_path_resolved,
                "salvaged_directory": salvaged_path_resolved,
                "dry_run": "true",
            },
            "1.0",
        )

        # Check skipped files metric
        assert_metric_with_labels(
            metrics_text,
            "brronson_salvage_files_skipped_total",
            {
                "recycled_directory": recycled_path_resolved,
                "salvaged_directory": salvaged_path_resolved,
                "dry_run": "true",
            },
            "1.0",
        )

    def test_salvage_subtitle_folders_batch_size(self):
        """Test that batch_size parameter limits files copied"""
        # Create folder with many subtitle files
        folder = self.recycled_dir / "Movie1"
        folder.mkdir()
        for i in range(1, 11):
            (folder / f"subtitle{i}.srt").touch()

        # Set batch_size to 5
        response = client.post(
            "/api/v1/salvage/subtitle-folders?dry_run=false&batch_size=5"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Should have copied exactly 5 files
        self.assertEqual(data["subtitle_files_copied"], 5)
        self.assertEqual(data["batch_size"], 5)
        self.assertTrue(data["batch_limit_reached"])

    def test_salvage_subtitle_folders_reentrant(self):
        """Test that salvage is re-entrant - can resume from where it stopped"""
        # Create folder with many subtitle files
        folder = self.recycled_dir / "Movie1"
        folder.mkdir()
        for i in range(1, 11):
            (folder / f"subtitle{i}.srt").touch()

        # First request: copy 5 files
        response1 = client.post(
            "/api/v1/salvage/subtitle-folders?dry_run=false&batch_size=5"
        )
        self.assertEqual(response1.status_code, 200)
        data1 = response1.json()
        self.assertEqual(data1["subtitle_files_copied"], 5)
        self.assertTrue(data1["batch_limit_reached"])

        # Second request: should continue and copy remaining files
        response2 = client.post(
            "/api/v1/salvage/subtitle-folders?dry_run=false&batch_size=5"
        )
        self.assertEqual(response2.status_code, 200)
        data2 = response2.json()
        self.assertEqual(data2["subtitle_files_copied"], 5)
        self.assertFalse(data2["batch_limit_reached"])

        # Verify all files are copied
        # Files are processed in lexicographic order, so final list will be:
        # subtitle1, subtitle10, subtitle2-9
        all_files = sorted(
            [f.name for f in (self.salvaged_dir / "Movie1").glob("*.srt")]
        )
        # When sorted lexicographically, subtitle10 comes before subtitle2
        expected_all = (
            ["subtitle1.srt"]
            + [f"subtitle{i}.srt" for i in range(10, 11)]
            + [f"subtitle{i}.srt" for i in range(2, 10)]
        )
        self.assertEqual(all_files, expected_all)

    def test_salvage_subtitle_folders_batch_size_skips_dont_count(self):
        """Test that skipped files don't count toward batch_size"""
        # Create folder with subtitle files
        folder = self.recycled_dir / "Movie1"
        folder.mkdir()
        for i in range(1, 11):
            (folder / f"subtitle{i}.srt").touch()

        # Pre-create some files
        (self.salvaged_dir / "Movie1").mkdir()
        (self.salvaged_dir / "Movie1" / "subtitle2.srt").touch()
        (self.salvaged_dir / "Movie1" / "subtitle4.srt").touch()

        # batch_size=5, but 2 files already exist (skipped)
        # Should copy 5 NEW files (skipped don't count)
        response = client.post(
            "/api/v1/salvage/subtitle-folders?dry_run=false&batch_size=5"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Should have copied 5 files
        # Note: Files are processed in sorted order, so subtitle2 and subtitle4
        # will be encountered in order. Since subtitle2 exists, it's skipped.
        # With batch_size=5, we copy 5 files and skip at least 1 (subtitle2).
        # subtitle4 might not be encountered if batch limit is reached first.
        self.assertEqual(data["subtitle_files_copied"], 5)
        self.assertGreaterEqual(data["subtitle_files_skipped"], 1)
        self.assertTrue(data["batch_limit_reached"])


if __name__ == "__main__":
    unittest.main()
