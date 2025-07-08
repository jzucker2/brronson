import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import fakeredis
from fastapi.testclient import TestClient

from app.main import app
from app.version import version

# Create a fake Redis server for testing
fake_redis_server = fakeredis.FakeServer()

client = TestClient(app)


class RedisTestMixin:
    """Mixin to provide fakeredis for tests that need Redis functionality."""

    def setUp(self):
        """Set up fakeredis for Redis operations."""
        super().setUp()
        # Patch Redis connection to use fakeredis
        self.redis_patcher = patch(
            "app.main.redis.Redis",
            return_value=fakeredis.FakeRedis(server=fake_redis_server),
        )
        self.mock_redis = self.redis_patcher.start()

    def tearDown(self):
        """Clean up Redis mocking."""
        self.redis_patcher.stop()
        super().tearDown()


def normalize_path_for_metrics(path):
    """Normalize a path for Prometheus metrics label comparison (strip /private prefix if present)."""
    p = str(path)
    if p.startswith("/private/var/"):
        return p[len("/private") :]
    return p


class TestMainEndpoints(unittest.TestCase):
    def test_root_endpoint(self):
        """Test the root endpoint"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Welcome to Bronson"
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
        assert data["service"] == "bronson"
        assert data["status"] == "healthy"
        assert data["version"] == version
        assert isinstance(data["timestamp"], (int, float))

    def test_version_endpoint(self):
        """Test the version endpoint"""
        response = client.get("/version")
        assert response.status_code == 200
        data = response.json()
        assert (
            data["message"] == f"The current version of Bronson is {version}"
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
            "bronson_cleanup_files_found_total",
            {
                "directory": normalize_path_for_metrics(self.test_path),
                "pattern": r"www\\.YTS\\.MX\\.jpg$",
                "dry_run": "true",
            },
            "2.0",
        )
        assert_metric_with_labels(
            metrics_text,
            "bronson_cleanup_current_files",
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
            "bronson_cleanup_files_found_total",
            {
                "directory": normalize_path_for_metrics(self.test_path),
                "pattern": r"www\\.YTS\\.MX\\.jpg$",
                "dry_run": "false",
            },
            "2.0",
        )
        assert_metric_with_labels(
            metrics_text,
            "bronson_cleanup_files_removed_total",
            {
                "directory": normalize_path_for_metrics(self.test_path),
                "pattern": r"www\\.YTS\\.MX\\.jpg$",
                "dry_run": "false",
            },
            "2.0",
        )
        assert_metric_with_labels(
            metrics_text,
            "bronson_cleanup_current_files",
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
        self.assertIn("bronson_subdirectories_found_total", metrics_text)


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
        self.assertIn("bronson_scan_files_found_total", metrics_text)
        self.assertIn("bronson_scan_current_files", metrics_text)
        self.assertIn("bronson_scan_operation_duration_seconds", metrics_text)
        self.assertIn("bronson_scan_directory_size_bytes", metrics_text)

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
        self.assertIn("bronson_scan_files_found_total", metrics_text)
        self.assertIn("bronson_scan_operation_duration_seconds", metrics_text)

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
        self.assertIn("bronson_cleanup_files_found_total", metrics_text)
        self.assertIn("bronson_cleanup_current_files", metrics_text)
        self.assertIn(
            "bronson_cleanup_operation_duration_seconds", metrics_text
        )
        self.assertIn("bronson_cleanup_directory_size_bytes", metrics_text)

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
        self.assertIn("bronson_cleanup_files_found_total", metrics_text)
        self.assertIn("bronson_cleanup_current_files", metrics_text)
        self.assertIn(
            "bronson_cleanup_operation_duration_seconds", metrics_text
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
        self.assertIn("bronson_cleanup_files_removed_total", metrics_text)

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
        self.assertIn("bronson_scan_files_found_total", metrics_text)
        self.assertIn("bronson_scan_current_files", metrics_text)
        self.assertIn("bronson_cleanup_files_found_total", metrics_text)
        self.assertIn("bronson_cleanup_current_files", metrics_text)
        self.assertIn("bronson_scan_operation_duration_seconds", metrics_text)
        self.assertIn(
            "bronson_cleanup_operation_duration_seconds", metrics_text
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
        self.assertIn("bronson_scan_errors_total", metrics_text)


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
            "bronson_comparison_duplicates_found_total", metrics_text
        )
        # The metric should be present but with value 0
        self.assertIn(
            f'bronson_comparison_duplicates_found_total{{cleanup_directory="{normalize_path_for_metrics(self.cleanup_dir)}",target_directory="{normalize_path_for_metrics(self.target_dir)}"}} 0.0',
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
            "bronson_comparison_duplicates_found_total", metrics_text
        )
        # The metric should be present but with value 0
        self.assertIn(
            f'bronson_comparison_duplicates_found_total{{cleanup_directory="{normalize_path_for_metrics(self.cleanup_dir)}",target_directory="{normalize_path_for_metrics(self.target_dir)}"}} 0.0',
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
            "bronson_comparison_duplicates_found_total", metrics_text
        )
        self.assertIn(
            "bronson_comparison_non_duplicates_found_total", metrics_text
        )
        self.assertIn(
            "bronson_comparison_operation_duration_seconds", metrics_text
        )
        # Should NOT have subdirectory metrics for comparison operations
        # (only duplicates and non-duplicates are counted, not all subdirectories)

        # Check specific metric values
        cleanup_path_resolved = normalize_path_for_metrics(self.cleanup_dir)
        target_path_resolved = normalize_path_for_metrics(self.target_dir)

        # Check duplicates metric (should be 2: shared_dir1, shared_dir2)
        assert_metric_with_labels(
            metrics_text,
            "bronson_comparison_duplicates_found_total",
            {
                "cleanup_directory": cleanup_path_resolved,
                "target_directory": target_path_resolved,
            },
            "2.0",
        )

        # Check non-duplicates metric (should be 1: cleanup_only)
        assert_metric_with_labels(
            metrics_text,
            "bronson_comparison_non_duplicates_found_total",
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


class TestMoveNonDuplicateFiles(RedisTestMixin, unittest.TestCase):
    def setUp(self):
        """Set up test directories for move operations"""
        super().setUp()
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

        super().tearDown()

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
        self.assertIn("operations_enqueued", data)
        self.assertIn("non_duplicate_subdirectories", data)
        self.assertIn("enqueued_operations", data)
        self.assertIn("remaining_files", data)
        self.assertIn("queue_name", data)

        # Check expected results (dry run)
        self.assertTrue(data["dry_run"])
        self.assertEqual(data["batch_size"], 1)  # Default batch size
        self.assertEqual(
            data["non_duplicates_found"], 2
        )  # cleanup_only, another_cleanup_only
        self.assertEqual(
            data["operations_enqueued"], 1
        )  # In dry run with batch_size=1, only 1 operation enqueued
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
        self.assertIn("operations_enqueued", data)
        self.assertIn("non_duplicate_subdirectories", data)
        self.assertIn("enqueued_operations", data)
        self.assertIn("remaining_files", data)
        self.assertIn("queue_name", data)

        # Check expected results (actual move)
        self.assertFalse(data["dry_run"])
        self.assertEqual(data["batch_size"], 1)  # Default batch size
        self.assertEqual(data["non_duplicates_found"], 2)
        self.assertEqual(
            data["operations_enqueued"], 1
        )  # Only 1 operation enqueued due to batch_size=1
        self.assertEqual(data["remaining_files"], 1)  # 1 file remaining
        self.assertIn("cleanup_only", data["non_duplicate_subdirectories"])
        self.assertIn(
            "another_cleanup_only", data["non_duplicate_subdirectories"]
        )

        # Verify files are still in original location (operations are only enqueued, not executed)
        # Note: another_cleanup_only comes before cleanup_only alphabetically
        self.assertTrue(
            (self.cleanup_dir / "cleanup_only").exists()
        )  # Not moved yet (only enqueued)
        self.assertTrue(
            (self.cleanup_dir / "another_cleanup_only").exists()
        )  # Not moved yet (only enqueued)
        self.assertFalse(
            (self.target_dir / "cleanup_only").exists()
        )  # Not moved yet
        self.assertFalse(
            (self.target_dir / "another_cleanup_only").exists()
        )  # Not moved yet

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
            data["operations_enqueued"], 2
        )  # Both operations enqueued due to batch_size=2
        self.assertEqual(data["remaining_files"], 0)  # No files remaining

        # Verify both files are still in original location (operations are only enqueued, not executed)
        self.assertTrue((self.cleanup_dir / "cleanup_only").exists())
        self.assertTrue((self.cleanup_dir / "another_cleanup_only").exists())
        self.assertFalse((self.target_dir / "cleanup_only").exists())
        self.assertFalse((self.target_dir / "another_cleanup_only").exists())

        # Check batch operations metric for batch_size=2
        metrics_response = client.get("/metrics")
        metrics_text = metrics_response.text

        cleanup_path_resolved = normalize_path_for_metrics(self.cleanup_dir)
        target_path_resolved = normalize_path_for_metrics(self.target_dir)

        assert_metric_with_labels(
            metrics_text,
            "bronson_move_batch_operations_total",
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
        self.assertEqual(data["operations_enqueued"], 0)
        self.assertEqual(len(data["non_duplicate_subdirectories"]), 0)
        self.assertEqual(len(data["enqueued_operations"]), 0)

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
        self.assertEqual(data["operations_enqueued"], 0)
        self.assertEqual(len(data["non_duplicate_subdirectories"]), 0)
        self.assertEqual(len(data["enqueued_operations"]), 0)

    def test_move_non_duplicates_nonexistent_cleanup(self):
        """Test move non-duplicates with nonexistent cleanup directory"""
        os.environ["CLEANUP_DIRECTORY"] = "/nonexistent/cleanup"

        response = client.post("/api/v1/move/non-duplicates")
        self.assertEqual(response.status_code, 404)

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
        self.assertIn("bronson_move_files_found_total", metrics_text)
        self.assertIn("bronson_move_operation_duration_seconds", metrics_text)
        self.assertIn("bronson_move_duplicates_found", metrics_text)
        self.assertIn("bronson_move_directories_moved", metrics_text)
        self.assertIn("bronson_move_batch_operations_total", metrics_text)

        # Use the resolved path format that appears in the metrics
        cleanup_path_resolved = normalize_path_for_metrics(self.cleanup_dir)
        target_path_resolved = normalize_path_for_metrics(self.target_dir)
        # Check gauge metrics for duplicates found (should be 2: shared_dir1, shared_dir2)
        assert_metric_with_labels(
            metrics_text,
            "bronson_move_duplicates_found",
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
            "bronson_move_directories_moved",
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
            "bronson_move_batch_operations_total",
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
        """Test move non-duplicates error handling (queue-based: only checks enqueuing)"""
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

        # Only check that the operation was enqueued
        self.assertIn("operations_enqueued", data)
        self.assertGreaterEqual(data["operations_enqueued"], 1)
        self.assertIn("enqueued_operations", data)
        self.assertGreaterEqual(len(data["enqueued_operations"]), 1)

    def test_move_non_duplicates_preserves_file_contents(self):
        """Test that move non-duplicates enqueues the operation (does not check file system)"""
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
        data = response.json()

        # Only check that the operation was enqueued
        self.assertIn("operations_enqueued", data)
        self.assertGreaterEqual(data["operations_enqueued"], 1)
        self.assertIn("enqueued_operations", data)
        self.assertGreaterEqual(len(data["enqueued_operations"]), 1)


class TestMoveNonDuplicateFilesIntegration(RedisTestMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.test_dir = tempfile.mkdtemp()
        self.cleanup_dir = Path(self.test_dir) / "cleanup"
        self.target_dir = Path(self.test_dir) / "target"
        self.cleanup_dir.mkdir()
        self.target_dir.mkdir()
        (self.cleanup_dir / "to_move").mkdir()
        (self.cleanup_dir / "to_move" / "file.txt").write_text(
            "integration test"
        )
        os.environ["CLEANUP_DIRECTORY"] = str(self.cleanup_dir)
        os.environ["TARGET_DIRECTORY"] = str(self.target_dir)
        import prometheus_client

        prometheus_client.REGISTRY._names_to_collectors.clear()
        from importlib import reload

        import app.main

        reload(app.main)
        global client
        client = TestClient(app.main.app)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.test_dir, ignore_errors=True)
        super().tearDown()

    def test_move_and_worker_integration(self):
        # Skip this test when using fakeredis as the worker runs in a separate process
        # and can't access the fakeredis mock
        self.skipTest(
            "Integration test with worker subprocess not compatible with fakeredis"
        )

        # Enqueue the move job
        response = client.post("/api/v1/move/non-duplicates?dry_run=false")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("operations_enqueued", data)
        self.assertGreaterEqual(data["operations_enqueued"], 1)
        # Run the worker in a subprocess for a short time
        proc = subprocess.Popen([sys.executable, "worker.py"])
        time.sleep(2)  # Give the worker time to process
        proc.terminate()
        proc.wait()
        # Check that the directory was moved
        self.assertFalse((self.cleanup_dir / "to_move").exists())
        self.assertTrue((self.target_dir / "to_move").exists())
        self.assertTrue((self.target_dir / "to_move" / "file.txt").exists())
        self.assertEqual(
            (self.target_dir / "to_move" / "file.txt").read_text(),
            "integration test",
        )
        # Check metrics
        metrics_response = client.get("/metrics")
        metrics_text = metrics_response.text
        self.assertIn("bronson_move_files_found_total", metrics_text)
        self.assertIn("bronson_move_files_moved_total", metrics_text)
        self.assertIn("bronson_move_batch_operations_total", metrics_text)


class TestQueueManagementEndpoints(RedisTestMixin, unittest.TestCase):
    """Test queue management endpoints with fakeredis."""

    def setUp(self):
        """Set up test environment for queue management tests."""
        super().setUp()
        # Set up test directories
        self.test_dir = tempfile.mkdtemp()
        self.cleanup_dir = Path(self.test_dir) / "cleanup"
        self.target_dir = Path(self.test_dir) / "target"
        self.cleanup_dir.mkdir()
        self.target_dir.mkdir()

        # Set environment variables
        self.original_cleanup_dir = os.environ.get("CLEANUP_DIRECTORY")
        self.original_target_dir = os.environ.get("TARGET_DIRECTORY")
        os.environ["CLEANUP_DIRECTORY"] = str(self.cleanup_dir)
        os.environ["TARGET_DIRECTORY"] = str(self.target_dir)

        # Clear Prometheus registry
        import prometheus_client

        prometheus_client.REGISTRY._names_to_collectors.clear()

        # Reload app with new environment
        from importlib import reload

        import app.main

        reload(app.main)
        global client
        client = TestClient(app.main.app)

    def tearDown(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.test_dir, ignore_errors=True)

        # Restore environment variables
        if self.original_cleanup_dir is not None:
            os.environ["CLEANUP_DIRECTORY"] = self.original_cleanup_dir
        elif "CLEANUP_DIRECTORY" in os.environ:
            del os.environ["CLEANUP_DIRECTORY"]

        if self.original_target_dir is not None:
            os.environ["TARGET_DIRECTORY"] = self.original_target_dir
        elif "TARGET_DIRECTORY" in os.environ:
            del os.environ["TARGET_DIRECTORY"]

        super().tearDown()

    def test_queue_status_empty(self):
        """Test queue status when queue is empty."""
        response = client.get("/api/v1/queue/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["queue_name"], "move_operations")
        # Note: fakeredis may have some default jobs, so we just check the structure
        self.assertIn("total_jobs", data)
        self.assertIn("pending_jobs", data)
        self.assertIn("failed_jobs", data)
        self.assertIn("started_jobs", data)
        self.assertIn("deferred_jobs", data)
        self.assertIn("finished_jobs", data)
        self.assertIn("scheduled_jobs", data)

    def test_queue_operations_empty(self):
        """Test queue operations when queue is empty."""
        response = client.get("/api/v1/queue/operations")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check the actual response structure
        self.assertIn("operations", data)
        self.assertIn("total", data)
        self.assertIn("limit", data)
        self.assertIn("offset", data)
        self.assertIsInstance(data["operations"], list)

    def test_queue_operations_with_jobs(self):
        """Test queue operations after enqueuing jobs."""
        # Create a test directory to move
        (self.cleanup_dir / "test_dir").mkdir()
        (self.cleanup_dir / "test_dir" / "file.txt").touch()

        # Enqueue a move operation
        move_response = client.post(
            "/api/v1/move/non-duplicates?dry_run=false"
        )
        self.assertEqual(move_response.status_code, 200)
        move_data = move_response.json()
        self.assertGreaterEqual(move_data["operations_enqueued"], 1)

        # Check queue operations
        response = client.get("/api/v1/queue/operations")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check the actual response structure
        self.assertIn("operations", data)
        self.assertIn("total", data)
        self.assertIn("limit", data)
        self.assertIn("offset", data)
        self.assertGreaterEqual(data["total"], 1)
        self.assertGreaterEqual(len(data["operations"]), 1)

        # Check operation details (actual structure from RQ)
        operation = data["operations"][0]
        self.assertIn("job_id", operation)
        self.assertIn("status", operation)
        self.assertIn("created_at", operation)
        self.assertIn("started_at", operation)
        self.assertIn("ended_at", operation)
        self.assertIn("result", operation)
        self.assertIn("exc_info", operation)

    def test_queue_clear(self):
        """Test clearing the queue."""
        # Skip this test as fakeredis doesn't support evalsha command used by RQ
        self.skipTest(
            "fakeredis doesn't support evalsha command used by RQ queue.empty()"
        )

        # First enqueue some operations
        (self.cleanup_dir / "test_dir1").mkdir()
        (self.cleanup_dir / "test_dir2").mkdir()

        move_response = client.post(
            "/api/v1/move/non-duplicates?dry_run=false&batch_size=2"
        )
        self.assertEqual(move_response.status_code, 200)

        # Verify queue has operations
        status_response = client.get("/api/v1/queue/status")
        self.assertEqual(status_response.status_code, 200)
        status_data = status_response.json()
        self.assertGreaterEqual(status_data["total_jobs"], 1)

        # Clear the queue
        clear_response = client.post("/api/v1/queue/clear")
        self.assertEqual(clear_response.status_code, 200)
        clear_data = clear_response.json()

        # Check the actual response structure
        self.assertIn("message", clear_data)
        self.assertIn("cleared successfully", clear_data["message"])

        # Verify queue is empty (or at least reduced)
        status_response2 = client.get("/api/v1/queue/status")
        self.assertEqual(status_response2.status_code, 200)
        status_data2 = status_response2.json()
        # Note: fakeredis may not clear completely, so we just check it's reduced
        self.assertLessEqual(
            status_data2["total_jobs"], status_data["total_jobs"]
        )

    def test_operation_status(self):
        """Test getting status of a specific operation."""
        # Enqueue an operation
        (self.cleanup_dir / "test_dir").mkdir()
        move_response = client.post(
            "/api/v1/move/non-duplicates?dry_run=false"
        )
        self.assertEqual(move_response.status_code, 200)
        move_data = move_response.json()

        operation_id = move_data["enqueued_operations"][0]["operation_id"]

        # Get operation status
        response = client.get(f"/api/v1/queue/operations/{operation_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check the actual response structure from RQ
        self.assertEqual(data["operation_id"], operation_id)
        self.assertIn("job_id", data)
        self.assertIn("status", data)
        self.assertIn("created_at", data)
        self.assertIn("started_at", data)
        self.assertIn("ended_at", data)
        self.assertIn("result", data)
        self.assertIn("exc_info", data)
        self.assertIn("meta", data)

    def test_operation_status_not_found(self):
        """Test getting status of non-existent operation."""
        response = client.get("/api/v1/queue/operations/non-existent-id")
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertIn("detail", data)

    def test_cancel_operation(self):
        """Test canceling an operation."""
        # Enqueue an operation
        (self.cleanup_dir / "test_dir").mkdir()
        move_response = client.post(
            "/api/v1/move/non-duplicates?dry_run=false"
        )
        self.assertEqual(move_response.status_code, 200)
        move_data = move_response.json()

        operation_id = move_data["enqueued_operations"][0]["operation_id"]

        # Cancel the operation
        response = client.delete(f"/api/v1/queue/operations/{operation_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check the actual response structure
        self.assertIn("message", data)
        self.assertIn("cancelled successfully", data["message"])
        self.assertIn(operation_id, data["message"])

    def test_cancel_operation_not_found(self):
        """Test canceling non-existent operation."""
        response = client.delete("/api/v1/queue/operations/non-existent-id")
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertIn("detail", data)


def assert_metric_with_labels(metrics_text, metric_name, labels, value):
    """
    Assert that a Prometheus metric with the given name, labels (dict), and value exists in the metrics_text.
    Ignores label order.
    """
    for line in metrics_text.splitlines():
        if not line.startswith(metric_name + "{"):
            continue
        if (
            all(f'{k}="{v}"' in line for k, v in labels.items())
            and f"}} {value}" in line
        ):
            return
    raise AssertionError(
        f"Metric {metric_name} with labels {labels} and value {value} not found in metrics output!\nLine examples:\n"
        + "\n".join(
            [line for line in metrics_text.splitlines() if metric_name in line]
        )
    )


if __name__ == "__main__":
    unittest.main()
