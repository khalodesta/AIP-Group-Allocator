"""Small Win32 ownership/job helpers. No shell, policy or elevated operations."""
import ctypes
from ctypes import wintypes


class BasicLimits(ctypes.Structure):
    _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                ("flags", wintypes.DWORD), ("minimum", ctypes.c_size_t),
                ("maximum", ctypes.c_size_t), ("active", wintypes.DWORD),
                ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                ("scheduling", wintypes.DWORD)]


class IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in ("reads", "writes", "other", "read_bytes", "write_bytes", "other_bytes")]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [("basic", BasicLimits), ("io", IoCounters),
                ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]


class Windows:
    def __init__(self):
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "OpenProcess": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
            "GetProcessTimes": ([wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4, wintypes.BOOL),
            "QueryFullProcessImageNameW": ([wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            "CreateJobObjectW": ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            "SetInformationJobObject": ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
            "AssignProcessToJobObject": ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            "GetCurrentProcess": ([], wintypes.HANDLE),
            "SetDllDirectoryW": ([wintypes.LPCWSTR], wintypes.BOOL),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.api, name)
            function.argtypes = arguments
            function.restype = result

    def identity(self, pid):
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            return None
        if pid <= 0:
            return None
        handle = self.api.OpenProcess(0x1000, False, pid)  # Query limited information only.
        if not handle:
            return None
        try:
            times = [wintypes.FILETIME() for _ in range(4)]
            path = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(path))
            if not self.api.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
                return None
            if not self.api.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
                return None
            return {"pid": pid, "created": times[0].dwLowDateTime | times[0].dwHighDateTime << 32,
                    "path": path.value.casefold()}
        finally:
            self.api.CloseHandle(handle)

    def own_process_tree(self, name):
        """Children inherit this job; closing the last handle kills only this tree.

        The supervisor joins before spawning children, avoiding an orphan race
        with PyInstaller's extraction child. Windows 8+ supports nested jobs.
        """
        handle = self.api.CreateJobObjectW(None, name)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.api.CloseHandle(handle)
            raise ctypes.WinError(ctypes.get_last_error())
        if not self.api.AssignProcessToJobObject(handle, self.api.GetCurrentProcess()):
            self.api.CloseHandle(handle)
            raise ctypes.WinError(ctypes.get_last_error())
        # Deliberately retained until supervisor exit; the OS closes it then.
        self.job_handle = handle

    def reset_dll_search(self):
        # Undo PyInstaller's private DLL search path before running bundled Node.
        if not self.api.SetDllDirectoryW(None):
            raise ctypes.WinError(ctypes.get_last_error())
