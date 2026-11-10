"""START/STOP supervisor for the offline Windows ZIP (standard library only)."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from urllib.request import ProxyHandler, Request, build_opener

from launcher_windows import Windows

URL = "http://localhost:3000"
START_TIMEOUT = 145
HTTP = build_opener(ProxyHandler({}))  # Local checks must never use a corporate proxy.


def healthy(url, api=False):
    try:
        with HTTP.open(Request(url, headers={"Cache-Control": "no-cache"}), timeout=1) as response:
            if response.status != 200:
                return False
            if api:
                data = json.loads(response.read(4096))
                return isinstance(data, dict) and data.get("status") == "healthy" and data.get("service") == "allocator-api"
            return True
    except (OSError, ValueError):
        return False


def port_in_use(port):
    for address in ("127.0.0.1", "::1"):
        try:
            with socket.create_connection((address, port), timeout=0.25):
                return True
        except OSError:
            pass
    return False


def same_process(saved, expected, windows):
    """PID alone is unsafe: require exact executable and process creation time."""
    return (isinstance(saved, dict) and saved.get("path") == str(expected.resolve()).casefold()
            and windows.identity(saved.get("pid")) == saved)


class Launcher:
    def __init__(self, root, windows=None):
        self.root = root.resolve()
        self.windows = windows or Windows()
        self.logs = self.root / "logs"
        self.runtime = self.root / ".runtime"
        self.state_file = self.runtime / "launcher.json"
        self.stop_file = self.runtime / "stop.request"
        self.error_file = self.logs / "launcher-error.log"
        self.executable = self.root / "app/launcher/allocator-launcher.exe"
        self.backend = self.root / "app/backend/allocator-backend.exe"
        self.node = self.root / "runtimes/node/node.exe"
        self.server = self.root / "app/frontend/server.js"
        self.logs.mkdir(exist_ok=True)
        self.runtime.mkdir(exist_ok=True)

    @contextmanager
    def operation_lock(self):
        import msvcrt
        with (self.runtime / "operation.lock").open("a+b") as handle:
            handle.write(b"0")
            handle.flush()
            deadline = time.monotonic() + START_TIMEOUT
            while True:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Another START or STOP is still busy. Please try again shortly.")
                    time.sleep(0.2)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

    def read_state(self):
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def write_state(self, data):
        temporary = self.state_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(data), encoding="utf-8")
        temporary.replace(self.state_file)

    def owned(self, state):
        return same_process(state.get("supervisor"), self.executable, self.windows)

    def ready(self, state):
        return (self.owned(state) and state.get("phase") == "ready"
                and same_process(state.get("backend"), self.backend, self.windows)
                and same_process(state.get("frontend"), self.node, self.windows)
                and healthy("http://127.0.0.1:8000/api/health", True)
                and healthy("http://127.0.0.1:3000")
                and healthy("http://127.0.0.1:3000/api/health", True))

    def open_browser(self):
        if os.environ.get("AIP_NO_BROWSER") != "1":
            self.windows.reset_dll_search()
            try:
                os.startfile(URL)
            except OSError:
                print(f"Please open {URL} in your browser.")

    def start(self):
        with self.operation_lock():
            for required in (self.executable, self.backend, self.node, self.server):
                if not required.is_file():
                    raise RuntimeError(f"Required application file is missing: {required.name}. Extract the entire ZIP again.")
            state = self.read_state()
            if self.ready(state):
                print("AIP Week 2 Allocator is already running.")
                self.open_browser()
                return
            if self.owned(state):
                raise RuntimeError("This application is starting or is unhealthy. Run STOP.bat, then START.bat again. See the logs folder.")
            stale = self.state_file.exists()
            self.state_file.unlink(missing_ok=True)
            self.stop_file.unlink(missing_ok=True)
            for port in (8000, 3000):
                if port_in_use(port):
                    note = "Stale process tracking was cleared. " if stale else ""
                    raise RuntimeError(f"{note}Port {port} is occupied by another program or another copy of the app. "
                                       "Nothing was stopped. Close the other copy with its STOP.bat, or contact the application administrator.")
            self.error_file.unlink(missing_ok=True)
            env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
            self.windows.reset_dll_search()
            with (self.logs / "supervisor.log").open("ab") as log:
                process = subprocess.Popen([str(self.executable), "serve"], cwd=self.root, env=env,
                    stdin=subprocess.DEVNULL, stdout=log, stderr=log, close_fds=True,
                    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
            deadline = time.monotonic() + START_TIMEOUT
            while time.monotonic() < deadline:
                state = self.read_state()
                if state.get("phase") == "ready" and self.ready(state):
                    print(f"AIP Week 2 Allocator is running. Open {URL}\nWhen finished, double-click STOP.bat.")
                    self.open_browser()
                    return
                if process.poll() is not None or self.error_file.exists():
                    detail = self.error_file.read_text(encoding="utf-8") if self.error_file.exists() else "The launcher exited before startup completed."
                    raise RuntimeError(detail.strip() + " See the logs folder.")
                time.sleep(0.3)
            # Request shutdown of this launch rather than leave hidden startup work.
            if self.owned(state):
                self.stop_file.write_text(state["token"], encoding="ascii")
            raise RuntimeError("Startup timed out. See logs, then run STOP.bat before trying again.")

    def stopping(self, token):
        try:
            return secrets.compare_digest(self.stop_file.read_text(encoding="ascii"), token)
        except (OSError, UnicodeError):
            return False

    def wait_service(self, child, url, token, api=False):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if self.stopping(token):
                raise RuntimeError("Startup was stopped.")
            if child.poll() is not None:
                raise RuntimeError("An application service exited during startup. See backend-error.log or frontend-error.log.")
            if healthy(url, api):
                return
            time.sleep(0.25)
        raise RuntimeError(f"An application service did not become ready: {url}. See the logs folder.")

    def serve(self):
        token = secrets.token_hex(24)
        self.windows.own_process_tree("Local\\AIP-" + token)
        state = {"token": token, "supervisor": self.windows.identity(os.getpid()), "phase": "starting"}
        children = []
        try:
            self.write_state(state)
            self.windows.reset_dll_search()
            env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1", HOSTNAME="127.0.0.1", PORT="3000",
                       NEXT_TELEMETRY_DISABLED="1", NODE_ENV="production",
                       AIP_STOP_FILE=str(self.stop_file), AIP_STOP_TOKEN=token)
            for name, command, directory, url, api in (
                ("backend", [str(self.backend)], self.backend.parent, "http://127.0.0.1:8000/api/health", True),
                ("frontend", [str(self.node), str(self.server)], self.server.parent, "http://127.0.0.1:3000", False),
            ):
                with (self.logs / f"{name}.log").open("ab") as out, (self.logs / f"{name}-error.log").open("ab") as err:
                    child = subprocess.Popen(command, cwd=directory, env=env, stdin=subprocess.DEVNULL,
                        stdout=out, stderr=err, close_fds=True, creationflags=subprocess.CREATE_NO_WINDOW)
                children.append(child)
                state[name] = self.windows.identity(child.pid)
                self.write_state(state)
                self.wait_service(child, url, token, api)
            if not healthy("http://127.0.0.1:3000/api/health", True):
                raise RuntimeError("The website cannot reach the allocation service. See the logs folder.")
            state["phase"] = "ready"
            self.write_state(state)
            while not self.stopping(token):
                if any(child.poll() is not None for child in children):
                    raise RuntimeError("An application service stopped unexpectedly. Run START.bat again; see the logs folder.")
                time.sleep(0.25)
        except Exception as exc:
            self.error_file.write_text(str(exc), encoding="utf-8")
            raise
        finally:
            self.stop_file.write_text(token, encoding="ascii")
            if children:
                try:
                    children[0].wait(timeout=8)  # Graceful FastAPI/bootloader cleanup.
                except subprocess.TimeoutExpired:
                    pass
            # No PID-based termination. Exiting the supervisor closes the job,
            # terminating exactly its backend/Node descendants (including bootloaders).
            if self.read_state().get("token") == token:
                self.state_file.unlink(missing_ok=True)
                self.stop_file.unlink(missing_ok=True)

    def stop(self):
        with self.operation_lock():
            state = self.read_state()
            if not self.owned(state):
                self.state_file.unlink(missing_ok=True)
                self.stop_file.unlink(missing_ok=True)
                print("The application is already stopped. Stale tracking, if any, was cleared; no other processes were stopped.")
                return
            self.stop_file.write_text(state["token"], encoding="ascii")
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if not self.owned(state):
                    print("AIP Week 2 Allocator has been stopped.")
                    return
                time.sleep(0.2)
            raise RuntimeError("The application did not stop within 20 seconds. See the logs folder and contact the application administrator.")


def main():
    if sys.platform != "win32":
        print("This launcher requires Windows x64.")
        return 1
    root = Path(sys.executable).resolve().parents[2]
    try:
        launcher = Launcher(root)
        command = sys.argv[1] if len(sys.argv) == 2 else ""
        if command not in {"start", "stop", "serve"}:
            raise RuntimeError("Use START.bat or STOP.bat from the extracted application folder.")
        getattr(launcher, command)()
        return 0
    except Exception as exc:
        print(f"\nAIP Week 2 Allocator: {exc}\nSee the logs folder or contact your application administrator.")
        try:
            (root / "logs/launcher-error.log").write_text(str(exc), encoding="utf-8")
        except OSError:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
