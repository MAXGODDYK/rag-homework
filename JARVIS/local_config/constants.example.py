"""Copy this file to constants.py and fill only local values."""

TELEGRAM_BOT_TOKEN = ""
OPENAI_API_KEY = ""
FREEMODEL_API_KEY = ""
HF_TOKEN = ""
LOCAL_ADAPTER_PATH = (
    r"C:\Все мои проэкты\qwen3-grounded-rag-finetuning"
    r"\artifacts\qwen3-4b-grounded-lora-v4"
)

# Optional public defaults can be overridden locally.
OPENAI_MODEL = "gpt-4.1-mini"
FREEMODEL_BASE_URL = "https://api.freemodel.dev/v1"
FREEMODEL_MODEL = "auto"
LOCAL_MODEL_NAME = "Qwen/Qwen3-4B-Instruct-2507"

# JARVIS owner/access configuration. Keep real IDs and paths local.
AUTHORIZED_TELEGRAM_USER_IDS = ""
ADMIN_TELEGRAM_USER_IDS = ""
JARVIS_ALLOWED_ROOTS = r"C:\path\to\project-one;C:\path\to\project-two"

# Optional integrations. Empty values keep the plugin disabled.
WEB_SEARCH_API_KEY = ""
GOOGLE_CLIENT_ID = ""
GOOGLE_CLIENT_SECRET = ""
GOOGLE_ACCESS_TOKEN = ""
MICROSOFT_CLIENT_ID = ""
MICROSOFT_TENANT_ID = "common"
MICROSOFT_ACCESS_TOKEN = ""

# Configurable local quotas.
JARVIS_MAX_UPLOAD_MB = 100
JARVIS_MAX_EXTRACTED_MB = 500
JARVIS_MAX_ARCHIVE_FILES = 10000
JARVIS_MAX_USER_STORAGE_MB = 1024
JARVIS_MAX_TOTAL_STORAGE_MB = 5120
JARVIS_MIN_FREE_DISK_GB = 20
