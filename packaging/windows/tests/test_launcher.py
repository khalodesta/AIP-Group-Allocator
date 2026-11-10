"""Launcher ownership/conflict regressions; no employee data or live app required."""
from contextlib import nullcontext
import ctypes
import importlib.util
import json
from pathlib import Path
import sys

import pytest

DIRECTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DIRECTORY))
spec = importlib.util.spec_from_file_location("portable_launcher", DIRECTORY / "portable_launcher.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class FakeWindows:
    def __init__(self, processes=None):
        self.processes = processes or {}

    def identity(self, pid):
        return self.processes.get(pid)


def test_pid_reuse_or_wrong_executable_is_never_owned(tmp_path):
    executable = tmp_path / "allocator-launcher.exe"
    saved = {"pid": 42, "path": str(executable.resolve()).casefold(), "created": 100}
    assert launcher.same_process(saved, executable, FakeWindows({42: saved}))
    assert not launcher.same_process(saved, executable, FakeWindows({42: dict(saved, created=200)}))
    assert not launcher.same_process(saved, tmp_path / "unrelated.exe", FakeWindows({42: saved}))
    assert not launcher.same_process(saved, executable, FakeWindows())


@pytest.mark.parametrize("body,expected", [(b'{"status":"healthy","service":"allocator-api"}', True),
    (b'{"status":"healthy"}', False), (b'[]', False), (b'not json', False)])
def test_health_requires_our_service_identity(monkeypatch, body, expected):
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def read(self, _limit): return body
    monkeypatch.setattr(launcher.HTTP, "open", lambda *_args, **_kwargs: Response())
    assert launcher.healthy("http://127.0.0.1:8000/api/health", True) is expected


def test_stale_tracking_is_cleared_without_sending_stop_to_unrelated_process(tmp_path, monkeypatch):
    app = launcher.Launcher(tmp_path, FakeWindows())
    monkeypatch.setattr(app, "operation_lock", nullcontext)
    app.state_file.write_text(json.dumps({"supervisor": {"pid": 123, "created": 1, "path": "unrelated.exe"}}))
    app.stop()
    assert not app.state_file.exists()
    assert not app.stop_file.exists()


@pytest.mark.parametrize("port", [8000, 3000])
def test_occupied_ports_fail_clearly_after_stale_tracking_cleanup(tmp_path, monkeypatch, port):
    app = launcher.Launcher(tmp_path, FakeWindows())
    for required in (app.executable, app.backend, app.node, app.server):
        required.parent.mkdir(parents=True, exist_ok=True)
        required.touch()
    monkeypatch.setattr(app, "operation_lock", nullcontext)
    monkeypatch.setattr(launcher, "port_in_use", lambda value: value == port)
    app.state_file.write_text('{"supervisor": {"pid": 123}}')
    with pytest.raises(RuntimeError, match=f"Stale process tracking was cleared.*Port {port}.*Nothing was stopped"):
        app.start()
    assert not app.state_file.exists()


def test_batch_entry_points_do_not_execute_powershell():
    for name in ("START.bat", "STOP.bat"):
        text = (DIRECTORY / name).read_text().casefold()
        assert "powershell" not in text and ".ps1" not in text
        assert '"%~dp0app\\launcher\\allocator-launcher.exe"' in text


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 ABI and live process query")
def test_windows_process_identity_and_job_structure():
    import os
    from launcher_windows import Windows, ExtendedLimits
    identity = Windows().identity(os.getpid())
    assert identity["path"] == str(Path(sys.executable).resolve()).casefold()
    assert identity["created"] > 0
    assert ctypes.sizeof(ExtendedLimits) == 144
