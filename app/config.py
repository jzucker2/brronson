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

# Default metadata/extras file extensions (case-insensitive)
DEFAULT_METADATA_EXTENSIONS = [
    ".nfo",
    ".sfv",
    ".srr",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
]

# Default movie/video file extensions (case-insensitive)
DEFAULT_MOVIE_EXTENSIONS = [
    ".avi",
    ".mkv",
    ".mp4",
    ".m4v",
    ".mov",
    ".wmv",
    ".flv",
    ".webm",
    ".mpg",
    ".mpeg",
    ".m2v",
    ".3gp",
    ".ogv",
    ".divx",
    ".xvid",
    ".rm",
    ".rmvb",
    ".vob",
    ".ts",
    ".mts",
    ".m2ts",
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


def get_migrated_movies_directory():
    """Get the migrated movies directory from environment variable"""
    return os.getenv("MIGRATED_MOVIES_DIRECTORY", "/migrated/movies")
