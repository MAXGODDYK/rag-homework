"""Copy this file to constants.py and fill only local values."""

# A provider is optional: without it JARVIS returns retrieved passages and
# citations in extractive mode.
OPENAI_API_KEY = ""
FREEMODEL_API_KEY = ""
HF_TOKEN = ""

OPENAI_MODEL = "gpt-4.1-mini"
FREEMODEL_BASE_URL = "https://api.freemodel.dev/v1"
FREEMODEL_MODEL = "auto"

# Local storage and ingestion quotas. These values are not committed when the
# example is copied to ignored constants.py.
JARVIS_MAX_UPLOAD_MB = 100
JARVIS_MAX_EXTRACTED_MB = 500
JARVIS_MAX_ARCHIVE_FILES = 10000
JARVIS_MAX_USER_STORAGE_MB = 1024
JARVIS_MAX_TOTAL_STORAGE_MB = 5120
JARVIS_MIN_FREE_DISK_GB = 20
