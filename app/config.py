"""Configuration functions and constants for the Brronson application."""

import os

# Default patterns for common unwanted files
DEFAULT_UNWANTED_PATTERNS = [
    r"www\.YTS\.MX\.jpg$",
    r"www\.YTS\.AM\.jpg$",
    r"www\.YTS\.LT\.jpg$",
    r"WWW\.YTS\.[A-Z]+\.jpg$",
    r"WWW\.YIFY-TORRENTS\.COM\.jpg$",
    r"YIFYStatus\.com\.txt$",
    r"YTSProxies\.com\.txt$",
    r"YTSYifyUP.*\(TOR\)\.txt$",
    r"\.DS_Store$",
    r"Thumbs\.db$",
    r"desktop\.ini$",
    r"\.tmp$",
    r"\.temp$",
    r"\.log$",
    r"\.cache$",
    r"\.bak$",
    r"\.backup$",
]

# Default subtitle file extensions (case-insensitive)
DEFAULT_SUBTITLE_EXTENSIONS = [
    ".srt",
    ".sub",
    ".vtt",
    ".ass",
    ".ssa",
    ".idx",
    ".sup",
    ".scc",
    ".ttml",
    ".dfxp",
    ".mcc",
    ".stl",
    ".sbv",
    ".smi",
    ".txt",  # Some subtitle files use .txt extension
]


def get_cleanup_directory():
    """Get the cleanup directory from environment variable"""
    return os.getenv("CLEANUP_DIRECTORY", "/data")


def get_target_directory():
    """Get the target directory from environment variable"""
    return os.getenv("TARGET_DIRECTORY", "/target")


def get_recycled_movies_directory():
    """Get the recycled movies directory from environment variable"""
    return os.getenv("RECYCLED_MOVIES_DIRECTORY", "/recycled/movies")


def get_salvaged_movies_directory():
    """Get the salvaged movies directory from environment variable"""
    return os.getenv("SALVAGED_MOVIES_DIRECTORY", "/salvaged/movies")
