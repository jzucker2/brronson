import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from tests.test_utils import normalize_path_for_metrics

client = TestClient(app)


class TestSharedHelperMethods(unittest.TestCase):
    """Test the shared helper methods"""

    def setUp(self):
        """Set up test directory"""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

        # Clear Prometheus default registry to avoid duplicate metrics
        import prometheus_client

        prometheus_client.REGISTRY._names_to_collectors.clear()

        # Import helper methods from their new locations
        from app.helpers import find_unwanted_files, validate_directory
        from app.config import DEFAULT_UNWANTED_PATTERNS

        self.validate_directory = validate_directory
        self.find_unwanted_files = find_unwanted_files
        self.DEFAULT_UNWANTED_PATTERNS = DEFAULT_UNWANTED_PATTERNS

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
        from app.helpers import get_subdirectories

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
