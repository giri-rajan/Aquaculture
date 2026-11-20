import os
import sys
import tempfile
from pathlib import Path

# Tests run against a throwaway database and never call Gemini
os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp()) / "test.db")
os.environ["DATA_SOURCE"] = "simulator"
os.environ["GEMINI_API_KEY"] = ""
# Whatever the developer's .env holds, tests never reach a model or a cloud database (dotenv does not override these)
for _k in ("VERTEX_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_CLOUD_PROJECT", "GEMMA_MODEL", "GEMINI_LIVE_MODEL",
           "FIRESTORE_ENABLED", "GCS_BUCKET", "APP_PASSWORD"):
    os.environ[_k] = ""
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
