"""CLI exit codes — use these instead of magic numbers."""

SUCCESS = 0
GENERAL_ERROR = 1
USAGE_ERROR = 2         # Invalid arguments, missing required config
FILE_NOT_FOUND = 3      # Input file doesn't exist
DEPENDENCY_MISSING = 4  # FFmpeg, yt-dlp, model files, etc.
RUNTIME_ERROR = 5       # API failure, processing error
REVIEW_REQUIRED = 6     # Natural timing needs explicit review before mix
PROVIDER_ERROR = 7      # TTS provider failed for one or more groups
