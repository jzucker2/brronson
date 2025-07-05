import unittest
import tempfile
import os
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.version import version

client = TestClient(app)


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
        print(metrics_text)

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
        assert data["directory"] == str(Path(self.test_dir).resolve())
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
        assert (self.test_path / "YTSProxies.com.txt").exists()
        assert (self.test_path / "YTSYifyUP123 (TOR).txt").exists()
        assert (self.test_path / ".DS_Store").exists()

    def test_cleanup_actual_removal(self):
        """Test cleanup endpoint with actual file removal"""
        response = client.post("/api/v1/cleanup/files?dry_run=false")
        assert response.status_code == 200
        data = response.json()

        assert data["dry_run"] is False
        assert data["files_found"] == 16
        assert data["files_removed"] == 16

        # Verify unwanted files are removed
        assert not (self.test_path / "www.YTS.MX.jpg").exists()
        assert not (self.test_path / "www.YTS.AM.jpg").exists()
        assert not (self.test_path / "www.YTS.LT.jpg").exists()
        assert not (self.test_path / "WWW.YTS.AG.jpg").exists()
        assert not (self.test_path / "WWW.YIFY-TORRENTS.COM.jpg").exists()
        assert not (self.test_path / "YIFYStatus.com.txt").exists()
        assert not (self.test_path / "YTSProxies.com.txt").exists()
        assert not (self.test_path / "YTSYifyUP123 (TOR).txt").exists()
        assert not (self.test_path / ".DS_Store").exists()
        assert not (
            self.test_path / "subdir" / "YTSYifyUP123 (TOR).txt"
        ).exists()  # noqa: E501
        assert not (self.test_path / "subdir" / "www.YTS.AM.jpg").exists()
        assert not (self.test_path / "subdir" / "www.YTS.LT.jpg").exists()
        assert not (self.test_path / "subdir" / "WWW.YTS.AG.jpg").exists()
        assert not (
            self.test_path / "subdir" / "WWW.YIFY-TORRENTS.COM.jpg"
        ).exists()  # noqa: E501
        assert not (self.test_path / "subdir" / "YTSProxies.com.txt").exists()

        # Verify normal files still exist
        assert (self.test_path / "normal_file.txt").exists()
        assert (self.test_path / "subdir" / "normal_file.txt").exists()

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
                self.test_path, str(self.test_path), "scan"
            )
        except Exception as e:
            self.fail(f"validate_directory raised {e} unexpectedly!")

    def test_validate_directory_nonexistent(self):
        """Test validate_directory with nonexistent directory"""
        nonexistent_path = Path("/nonexistent/test/directory")
        with self.assertRaises(Exception):
            self.validate_directory(
                nonexistent_path, str(nonexistent_path), "scan"
            )

    def test_validate_directory_system_protection(self):
        """Test validate_directory with protected system directory"""
        system_path = Path("/etc")
        with self.assertRaises(Exception):
            self.validate_directory(system_path, str(system_path), "scan")

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
        self.assertIn("bronson_cleanup_files_found_total", metrics_text)
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
        """Test successful directory comparison"""
        response = client.get("/api/v1/compare/directories")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check response structure
        self.assertIn("cleanup_directory", data)
        self.assertIn("target_directory", data)
        self.assertIn("cleanup_subdirectories", data)
        self.assertIn("target_subdirectories", data)
        self.assertIn("duplicate_count", data)
        self.assertIn("duplicates", data)
        self.assertIn("cleanup_only", data)
        self.assertIn("target_only", data)

        # Check expected results
        self.assertEqual(data["duplicate_count"], 2)
        self.assertIn("shared_dir1", data["duplicates"])
        self.assertIn("shared_dir2", data["duplicates"])
        self.assertIn("cleanup_only", data["cleanup_only"])
        self.assertIn("target_only", data["target_only"])

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

        self.assertEqual(data["duplicate_count"], 0)
        self.assertEqual(len(data["duplicates"]), 0)

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

        self.assertEqual(data["duplicate_count"], 0)
        self.assertEqual(len(data["cleanup_subdirectories"]), 0)
        self.assertEqual(len(data["target_subdirectories"]), 0)

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
            "bronson_comparison_operation_duration_seconds", metrics_text
        )
        # Should have subdirectory metrics
        self.assertIn("bronson_subdirectories_found_total", metrics_text)

    def test_compare_directories_with_files(self):
        """Test that directory comparison
        only looks at directories, not files"""
        # Add some files to the directories
        (self.cleanup_dir / "test_file.txt").touch()
        (self.target_dir / "test_file.txt").touch()
        (self.cleanup_dir / "another_file.jpg").touch()

        response = client.get("/api/v1/compare/directories")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Files should not be included in subdirectories
        self.assertNotIn("test_file.txt", data["cleanup_subdirectories"])
        self.assertNotIn("test_file.txt", data["target_subdirectories"])
        another_file = "another_file.jpg"
        cleanup_subdirs = data["cleanup_subdirectories"]
        self.assertNotIn(another_file, cleanup_subdirs)


if __name__ == "__main__":
    unittest.main()
