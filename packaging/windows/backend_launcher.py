"""Local, localhost-only entry point used by the portable Windows release."""

import sys
from pathlib import Path

import uvicorn


def bundled_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))


BACKEND_ROOT = bundled_root() / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import app  # noqa: E402


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, access_log=False, log_level="warning")
