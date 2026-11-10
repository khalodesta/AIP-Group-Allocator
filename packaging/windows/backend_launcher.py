"""Local, localhost-only entry point used by the portable Windows release."""

import sys
import os
import threading
import time
from pathlib import Path

import uvicorn


def bundled_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))


BACKEND_ROOT = bundled_root() / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import app  # noqa: E402


if __name__ == "__main__":
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8000,
                                          access_log=False, log_level="warning"))
    def watch_stop():
        # Graceful shutdown lets the bootloader clean its extraction directory.
        stop_file, token = os.environ.get("AIP_STOP_FILE"), os.environ.get("AIP_STOP_TOKEN")
        if not stop_file or not token:
            return
        while not server.should_exit:
            try:
                if Path(stop_file).read_text(encoding="ascii") == token:
                    server.should_exit = True
                    return
            except (OSError, UnicodeError):
                pass
            time.sleep(0.2)
    threading.Thread(target=watch_stop, daemon=True).start()
    server.run()
