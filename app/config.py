import os
import secrets
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RUNTIME_DIR = Path(tempfile.gettempdir()) / "4pmspike" if os.getenv("VERCEL") else BASE_DIR
DATA_DIR = RUNTIME_DIR / "data"
EXPORTS_DIR = RUNTIME_DIR / "exports"
MODELS_DIR = RUNTIME_DIR / "saved_models"

DATA_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)

SECRET_KEY = os.getenv("DSS_SECRET_KEY")
if not SECRET_KEY:
    if os.getenv("VERCEL"):
        raise RuntimeError("DSS_SECRET_KEY must be configured in the Vercel environment.")
    SECRET_KEY = secrets.token_urlsafe(32)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12  # 12-hour operational shift

DATABASE_URL = f"sqlite:///{RUNTIME_DIR / 'dss_campus.db'}"

# Energy analysis parameters
PEAK_WINDOW_START_HOUR = 16  # 16:00 inclusive
PEAK_WINDOW_END_HOUR = 20    # 20:00 exclusive
INTERVAL_MINUTES = 15
EXPECTED_PEAK_INTERVALS_PER_DAY = (PEAK_WINDOW_END_HOUR - PEAK_WINDOW_START_HOUR) * (60 // INTERVAL_MINUTES) # 16 intervals
COMPLETENESS_THRESHOLD = 0.90 # 90% minimum completeness
RULE_VERSION = "DSS-CORE-V1.0"
