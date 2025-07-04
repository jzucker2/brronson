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
        assert (self.test_path / "subdir" / "YTSYifyUP123 (TOR).txt").exists()  # noqa: E501
        assert (self.test_path / "subdir" / "www.YTS.AM.jpg").exists()
        assert (self.test_path / "subdir" / "www.YTS.LT.jpg").exists()
        assert (self.test_path / "subdir" / "WWW.YTS.AG.jpg").exists()
        assert (self.test_path / "subdir" / "WWW.YIFY-TORRENTS.COM.jpg").exists()  # noqa: E501
        assert (self.test_path / "subdir" / "YTSProxies.com.txt").exists()

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
        assert not (self.test_path / "subdir" / "YTSYifyUP123 (TOR).txt").exists()  # noqa: E501
        assert not (self.test_path / "subdir" / "www.YTS.AM.jpg").exists()
        assert not (self.test_path / "subdir" / "www.YTS.LT.jpg").exists()
        assert not (self.test_path / "subdir" / "WWW.YTS.AG.jpg").exists()
        assert not (self.test_path / "subdir" / "WWW.YIFY-TORRENTS.COM.jpg").exists()  # noqa: E501
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


if __name__ == "__main__":
    unittest.main()
