"""Copy this file to constants.py and fill only local values."""

# Hugging Face is optional and is used only when local embedding or reranker
# weights need to be downloaded. It is not a generation-provider key.
HF_TOKEN = ""

# JARVIS sends generation only to this local Ollama endpoint.
OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "qwen3:14b"

# Google Sheets is optional until you connect the chunks database in Settings.
# Never commit the service-account JSON file or its path for another computer.
JARVIS_GOOGLE_SERVICE_ACCOUNT_PATH = ""
JARVIS_GOOGLE_OWNER_EMAIL = ""
JARVIS_GOOGLE_SPREADSHEET_ID = ""

# Local storage and ingestion quotas. These values are not committed when the
# example is copied to ignored constants.py.
JARVIS_MAX_UPLOAD_MB = 100
JARVIS_MAX_EXTRACTED_MB = 500
JARVIS_MAX_ARCHIVE_FILES = 10000
JARVIS_MAX_USER_STORAGE_MB = 1024
JARVIS_MAX_TOTAL_STORAGE_MB = 5120
JARVIS_MIN_FREE_DISK_GB = 20
