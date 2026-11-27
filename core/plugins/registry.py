import ast
import asyncio
import ctypes
import importlib
import importlib.util
import inspect
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Type

from core.plugins.sdk import (
    ALLOWED_PLUGIN_PERMISSIONS,
    DEFAULT_PLUGIN_PERMISSIONS,
    MaybeAIPlugin,
    PluginContext,
    PluginManifest,
)


BUILTIN_MODULES: Tuple[str, ...] = ("core.plugins.word_chain",)
REPO_ROOT: Path = Path(__file__).resolve().parents[2]
VALID_SANDBOX_MODES: Tuple[str, ...] = ("subprocess", "inprocess")

SANDBOX_LEVEL_OS_ISOLATED = "os_isolated"
SANDBOX_LEVEL_SUBPROCESS_RESTRICTED = "subprocess_restricted"
SANDBOX_LEVEL_BLOCKED = "blocked"
SANDBOX_LEVEL_BUILTIN = "builtin"


class _WindowsJobObject:
    """Best-effort Windows Job Object wrapper enforcing memory, process-count, and kill-on-close limits."""

    def __init__(self, handle: Any) -> None:
        self._handle = handle
        self._kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    @classmethod
    def attach(
        cls,
        pid: int,
        memory_limit_mb: int = 512,
        max_processes: int = 1,
    ) -> Tuple[Optional["_WindowsJobObject"], str]:
        if os.name != "nt":
            return None, "not_windows"
        try:
            from ctypes import wintypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

            class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD),
                ]

            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("ReadOperationCount", ctypes.c_uint64),
                    ("WriteOperationCount", ctypes.c_uint64),
                    ("OtherOperationCount", ctypes.c_uint64),
                    ("ReadTransferCount", ctypes.c_uint64),
                    ("WriteTransferCount", ctypes.c_uint64),
                    ("OtherTransferCount", ctypes.c_uint64),
                ]

            class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                    ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            class JOBOBJECT_BASIC_UI_RESTRICTIONS(ctypes.Structure):
                _fields_ = [
                    ("UIRestrictionsClass", wintypes.DWORD),
                ]

            JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
            JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
            JobObjectBasicUIRestrictions = 4
            JobObjectExtendedLimitInformation = 9
            JOB_OBJECT_UILIMIT_HANDLES = 0x00000001
            JOB_OBJECT_UILIMIT_READCLIPBOARD = 0x00000002
            JOB_OBJECT_UILIMIT_WRITECLIPBOARD = 0x00000004
            JOB_OBJECT_UILIMIT_SYSTEMPARAMETERS = 0x00000008
            JOB_OBJECT_UILIMIT_DISPLAYSETTINGS = 0x00000010
            JOB_OBJECT_UILIMIT_GLOBALATOMS = 0x00000020
            JOB_OBJECT_UILIMIT_DESKTOP = 0x00000040
            JOB_OBJECT_UILIMIT_EXITWINDOWS = 0x00000080
            PROCESS_SET_QUOTA = 0x0100
            PROCESS_TERMINATE = 0x0001

            kernel32.CreateJobObjectW.restype = wintypes.HANDLE
            kernel32.OpenProcess.restype = wintypes.HANDLE

            job_handle = kernel32.CreateJobObjectW(None, None)
            if not job_handle:
                return None, "windows_job_create_failed"

            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = (
                JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                | JOB_OBJECT_LIMIT_PROCESS_MEMORY
                | JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            )
            info.BasicLimitInformation.ActiveProcessLimit = max_processes
            info.ProcessMemoryLimit = memory_limit_mb * 1024 * 1024

            ok_set = kernel32.SetInformationJobObject(
                job_handle,
                JobObjectExtendedLimitInformation,
                ctypes.byref(info),
                ctypes.sizeof(info),
            )
            if not ok_set:
                kernel32.CloseHandle(job_handle)
                return None, "windows_job_setinfo_failed"

            ui_info = JOBOBJECT_BASIC_UI_RESTRICTIONS()
            ui_info.UIRestrictionsClass = (
                JOB_OBJECT_UILIMIT_HANDLES
                | JOB_OBJECT_UILIMIT_READCLIPBOARD
                | JOB_OBJECT_UILIMIT_WRITECLIPBOARD
                | JOB_OBJECT_UILIMIT_SYSTEMPARAMETERS
                | JOB_OBJECT_UILIMIT_DISPLAYSETTINGS
                | JOB_OBJECT_UILIMIT_GLOBALATOMS
                | JOB_OBJECT_UILIMIT_DESKTOP
                | JOB_OBJECT_UILIMIT_EXITWINDOWS
            )
            ok_ui = kernel32.SetInformationJobObject(
                job_handle,
                JobObjectBasicUIRestrictions,
                ctypes.byref(ui_info),
                ctypes.sizeof(ui_info),
            )
            if not ok_ui:
                kernel32.CloseHandle(job_handle)
                return None, "windows_job_setui_failed"

            proc_handle = kernel32.OpenProcess(
                PROCESS_SET_QUOTA | PROCESS_TERMINATE,
                False,
                int(pid),
            )
            if not proc_handle:
                kernel32.CloseHandle(job_handle)
                return None, "windows_open_process_failed"

            try:
                ok_assign = kernel32.AssignProcessToJobObject(job_handle, proc_handle)
            finally:
                kernel32.CloseHandle(proc_handle)

            if not ok_assign:
                kernel32.CloseHandle(job_handle)
                return None, "windows_job_assign_failed"

            return cls(job_handle), "windows_job_object"
        except Exception as exc:
            return None, f"windows_job_error:{type(exc).__name__}"

    def close(self) -> None:
        if self._handle:
            try:
                self._kernel32.CloseHandle(self._handle)
            except Exception:
                pass
            self._handle = None


class _SandboxRPCError(RuntimeError):
    """Error returned by the sandboxed plugin worker over JSON-RPC 2.0."""

    def __init__(self, message: str, error_type: str = "PluginError", code: int = -32000) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.code = code


class _SandboxPluginClient:
    """Host-side JSON-RPC 2.0 client managing a single sandboxed plugin subprocess."""

    def __init__(
        self,
        plugin_id: str,
        source_path: Path,
        env: Dict[str, str],
        permission_provider: Callable[[], List[str]],
        scratch_dir: Optional[Path] = None,
        speak_cb: Optional[Callable[[str, str], Awaitable[Any]]] = None,
        broadcast_cb: Optional[Callable[[str, Dict[str, Any]], Awaitable[Any]]] = None,
        event_bus_provider: Optional[Callable[[], Any]] = None,
    ) -> None:
        self.plugin_id = plugin_id
        self.source_path = Path(source_path).resolve()
        if scratch_dir is not None:
            self.scratch_dir = Path(scratch_dir).resolve()
        else:
            safe_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(plugin_id or "plugin")).strip("_") or "plugin"
            self.scratch_dir = (Path(tempfile.gettempdir()) / "maybeai_plugin_sandbox" / safe_id).resolve()
        self.env = dict(env)
        self._permission_provider = permission_provider
        self._speak_cb = speak_cb
        self._broadcast_cb = broadcast_cb
        self._event_bus_provider = event_bus_provider

        self.proc: Optional[asyncio.subprocess.Process] = None
        self._win_job: Optional[_WindowsJobObject] = None
        self.sandbox_level: str = SANDBOX_LEVEL_SUBPROCESS_RESTRICTED
        self.os_isolation_detail: str = "pending"
        self._pending: Dict[str, asyncio.Future] = {}
        self._req_seq = 0
        self._write_lock = asyncio.Lock()
        self._reader_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._last_stderr: List[str] = []

    @property
    def is_running(self) -> bool:
        return self.proc is not None and self.proc.returncode is None

    async def start(self) -> None:
        if self.is_running:
            return
        self.scratch_dir.mkdir(parents=True, exist_ok=True)
        perms = [str(p).strip() for p in (self._permission_provider() or []) if str(p).strip()]
        worker_exe = sys.executable
        launch_env = dict(self.env)
        if os.name == "nt":
            base_exe = getattr(sys, "_base_executable", None)
            if base_exe and Path(base_exe).exists() and Path(base_exe) != Path(sys.executable):
                # Bypass Windows venvlauncher.exe stub so ActiveProcessLimit=1 applies to the worker alone.
                worker_exe = str(base_exe)
                launch_env.setdefault("__PYVENV_LAUNCHER__", sys.executable)

        worker_cmd: List[str] = [
            worker_exe,
            "-m",
            "core.plugins.sandbox_worker",
            str(self.source_path),
            f"--scratch-dir={self.scratch_dir}",
            f"--repo-root={REPO_ROOT}",
            f"--permissions={','.join(perms)}",
        ]

        launch_cmd = list(worker_cmd)
        used_bwrap = False
        if os.name != "nt":
            bwrap_bin = shutil.which("bwrap")
            if bwrap_bin:
                bwrap_cmd: List[str] = [
                    bwrap_bin,
                    "--die-with-parent",
                    "--new-session",
                ]
                if "net:outbound" not in perms and "network:outbound" not in perms:
                    bwrap_cmd.append("--unshare-net")
                for ro_path in ("/usr", "/lib", "/lib64", "/bin", "/etc/alternatives"):
                    if Path(ro_path).exists():
                        bwrap_cmd.extend(["--ro-bind", ro_path, ro_path])
                bwrap_cmd.extend(["--ro-bind", str(REPO_ROOT / "core" / "plugins"), str(REPO_ROOT / "core" / "plugins")])
                bwrap_cmd.extend(["--ro-bind", str(self.source_path), str(self.source_path)])
                bwrap_cmd.extend(["--bind", str(self.scratch_dir), str(self.scratch_dir)])
                bwrap_cmd.extend(["--chdir", str(self.scratch_dir)])
                bwrap_cmd.extend(worker_cmd)
                bwrap_cmd.append("--bwrap-active")
                launch_cmd = bwrap_cmd
                used_bwrap = True

        try:
            self.proc = await asyncio.create_subprocess_exec(
                *launch_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=launch_env,
                cwd=str(self.scratch_dir),
            )
        except OSError:
            if not used_bwrap:
                raise
            used_bwrap = False
            self.proc = await asyncio.create_subprocess_exec(
                *worker_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=launch_env,
                cwd=str(self.scratch_dir),
            )

        if os.name == "nt":
            job, detail = _WindowsJobObject.attach(self.proc.pid)
            self._win_job = job
            self.os_isolation_detail = detail
            self.sandbox_level = (
                SANDBOX_LEVEL_OS_ISOLATED
                if job is not None
                else SANDBOX_LEVEL_SUBPROCESS_RESTRICTED
            )
        elif used_bwrap:
            self.sandbox_level = SANDBOX_LEVEL_OS_ISOLATED
            self.os_isolation_detail = "linux_bwrap"
        elif sys.platform.startswith("linux"):
            self.sandbox_level = SANDBOX_LEVEL_OS_ISOLATED
            self.os_isolation_detail = "linux_rlimit"
        else:
            self.sandbox_level = SANDBOX_LEVEL_SUBPROCESS_RESTRICTED
            self.os_isolation_detail = "posix_boundary_guard"

        self._reader_task = asyncio.create_task(self._stdout_reader_loop())
        self._stderr_task = asyncio.create_task(self._stderr_drain_loop())

    async def _send_json(self, payload: Dict[str, Any]) -> None:
        if self.proc is None or self.proc.stdin is None:
            raise RuntimeError("Sandbox worker stdin is not available")
        data = (json.dumps(payload, ensure_ascii=False, default=str) + "\n").encode("utf-8")
        async with self._write_lock:
            self.proc.stdin.write(data)
            await self.proc.stdin.drain()

    async def call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        if not self.is_running:
            await self.start()
        loop = asyncio.get_running_loop()
        self._req_seq += 1
        req_id = f"h-{self._req_seq}"
        fut: asyncio.Future = loop.create_future()
        self._pending[req_id] = fut
        try:
            await self._send_json(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "method": method,
                    "params": params or {},
                }
            )
            return await fut
        finally:
            self._pending.pop(req_id, None)

    async def _stdout_reader_loop(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        try:
            while True:
                raw_line = await self.proc.stdout.readline()
                if not raw_line:
                    break
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(msg, dict):
                    continue

                if "method" in msg:
                    asyncio.create_task(self._handle_worker_callback(msg))
                    continue

                if "id" in msg:
                    req_id = str(msg["id"])
                    fut = self._pending.pop(req_id, None)
                    if fut is None or fut.done():
                        continue
                    if "error" in msg and msg["error"] is not None:
                        err = msg["error"]
                        if isinstance(err, dict):
                            err_msg = str(err.get("message", "Worker RPC error"))
                            err_type = str((err.get("data") or {}).get("error_type", "PluginError"))
                            code = int(err.get("code", -32000))
                        else:
                            err_msg = str(err)
                            err_type = "PluginError"
                            code = -32000
                        fut.set_exception(_SandboxRPCError(err_msg, error_type=err_type, code=code))
                    else:
                        fut.set_result(msg.get("result"))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(exc)
        finally:
            stderr_tail = " | ".join(self._last_stderr[-5:])
            err_msg = f"Sandbox worker '{self.plugin_id}' exited" + (f": {stderr_tail}" if stderr_tail else "")
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(EOFError(err_msg))
            self._pending.clear()

    async def _stderr_drain_loop(self) -> None:
        assert self.proc is not None and self.proc.stderr is not None
        try:
            while True:
                line = await self.proc.stderr.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    self._last_stderr.append(text)
                    if len(self._last_stderr) > 20:
                        self._last_stderr = self._last_stderr[-20:]
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    async def _send_callback_reply(
        self,
        req_id: Any,
        result: Any = None,
        error: Optional[Dict[str, Any]] = None,
    ) -> None:
        if req_id is None:
            return
        payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": req_id}
        if error is not None:
            payload["error"] = error
        else:
            payload["result"] = result
        try:
            await self._send_json(payload)
        except Exception:
            pass

    async def _handle_worker_callback(self, msg: Dict[str, Any]) -> None:
        req_id = msg.get("id")
        method = str(msg.get("method", ""))
        params = msg.get("params")
        if not isinstance(params, dict):
            params = {}

        perms = set(self._permission_provider() or [])
        event_bus = self._event_bus_provider() if self._event_bus_provider else None

        try:
            if method == "ctx.speak":
                if "tts:speak" not in perms:
                    await self._send_callback_reply(
                        req_id,
                        error={
                            "code": -32003,
                            "message": f"Permission denied: 'tts:speak' required for speak (plugin={self.plugin_id})",
                        },
                    )
                    return
                text = str(params.get("text", "") or "").strip()
                emotion = str(params.get("emotion", "neutral") or "neutral")
                if text:
                    if self._speak_cb is not None:
                        res = self._speak_cb(text, emotion)
                        if inspect.isawaitable(res):
                            await res
                    elif event_bus is not None:
                        await event_bus.publish(
                            "plugin.event",
                            {
                                "plugin_id": self.plugin_id,
                                "kind": "speak",
                                "text": text,
                                "emotion": emotion,
                            },
                        )
                await self._send_callback_reply(req_id, result={"ok": True})
                return

            if method == "ctx.broadcast":
                if "event:pub" not in perms:
                    await self._send_callback_reply(
                        req_id,
                        error={
                            "code": -32003,
                            "message": f"Permission denied: 'event:pub' required for broadcast (plugin={self.plugin_id})",
                        },
                    )
                    return
                event_type = str(params.get("event_type", ""))
                data = dict(params.get("data") or {})
                if self._broadcast_cb is not None:
                    res = self._broadcast_cb(event_type, data)
                    if inspect.isawaitable(res):
                        await res
                elif event_bus is not None:
                    await event_bus.publish(
                        "plugin.event",
                        {
                            "plugin_id": self.plugin_id,
                            "kind": "broadcast",
                            "event_type": event_type,
                            "data": data,
                        },
                    )
                await self._send_callback_reply(req_id, result={"ok": True})
                return

            if method == "event_bus.publish":
                if "event:pub" not in perms:
                    await self._send_callback_reply(
                        req_id,
                        error={
                            "code": -32003,
                            "message": f"Permission denied: 'event:pub' required for event_bus.publish (plugin={self.plugin_id})",
                        },
                    )
                    return
                event_type = str(params.get("event_type", ""))
                data = dict(params.get("data") or {})
                if event_bus is not None:
                    await event_bus.publish(event_type, data)
                await self._send_callback_reply(req_id, result={"ok": True})
                return

            await self._send_callback_reply(
                req_id,
                error={"code": -32601, "message": f"Unknown host callback '{method}'"},
            )
        except Exception as exc:
            await self._send_callback_reply(
                req_id,
                error={"code": -32000, "message": f"{type(exc).__name__}: {exc}"},
            )

    async def kill_and_cleanup(self) -> None:
        proc = self.proc
        if proc is not None:
            if proc.returncode is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except Exception:
                    pass
            if proc.stdin is not None:
                try:
                    proc.stdin.close()
                except Exception:
                    pass
        for task in (self._reader_task, self._stderr_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        self._reader_task = None
        self._stderr_task = None
        self.proc = None
        if self._win_job is not None:
            self._win_job.close()
            self._win_job = None

    async def graceful_shutdown(self, timeout: float = 2.0) -> None:
        if self.is_running:
            try:
                await asyncio.wait_for(self.call("shutdown", {}), timeout=timeout)
                if self.proc is not None:
                    await asyncio.wait_for(self.proc.wait(), timeout=timeout)
            except Exception:
                pass
        await self.kill_and_cleanup()


class PluginRegistry:
    """
    Manages discovery, manifest validation, lifecycle, EventBus integration,
    timeout enforcement, and exception/process isolation for built-in and external plugins.
    """

    def __init__(
        self,
        plugins_dir: str = "plugins",
        enabled_plugins: Optional[List[str]] = None,
        hook_timeout_sec: float = 5.0,
        startup_timeout_sec: float = 5.0,
        enabled: bool = True,
        sandbox_mode: str = "subprocess",
        granted_permissions: Optional[Dict[str, List[str]]] = None,
        event_bus: Optional[Any] = None,
        speak_cb: Optional[Callable[[str, str], Awaitable[Any]]] = None,
        broadcast_cb: Optional[Callable[[str, Dict[str, Any]], Awaitable[Any]]] = None,
        settings: Optional[Dict[str, Any]] = None,
    ):
        self.plugins_dir = Path(plugins_dir)
        self.enabled: bool = bool(enabled)
        self.enabled_plugins: List[str] = (
            list(enabled_plugins) if enabled_plugins is not None else ["word_chain"]
        )
        self.hook_timeout_sec: float = max(0.1, float(hook_timeout_sec or 5.0))
        self.startup_timeout_sec: float = max(0.5, float(startup_timeout_sec or 5.0))
        self.sandbox_mode: str = self._normalize_sandbox_mode(sandbox_mode)
        self.granted_permissions: Dict[str, List[str]] = self._normalize_granted_permissions(
            granted_permissions
        )
        self._sandbox_root: Path = Path(tempfile.gettempdir()) / "maybeai_plugin_sandbox"
        self.event_bus = event_bus
        self._speak_cb = speak_cb
        self._broadcast_cb = broadcast_cb

        self._plugins: Dict[str, MaybeAIPlugin] = {}
        self._manifests: Dict[str, PluginManifest] = {}
        self._subprocesses: Dict[str, _SandboxPluginClient] = {}
        self._contexts: Dict[str, PluginContext] = {}
        self._plugin_states: Dict[str, Dict[str, Any]] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self._sources: Dict[str, Dict[str, Any]] = {}
        self._command_map: Dict[str, str] = {}
        self._bus_attached: bool = False

        if settings:
            self.update_config(settings)

    @staticmethod
    def _normalize_granted_permissions(raw: Any) -> Dict[str, List[str]]:
        if not isinstance(raw, dict):
            return {}
        normalized: Dict[str, List[str]] = {}
        for pid, perms in raw.items():
            key = str(pid or "").strip()
            if not key or not isinstance(perms, (list, tuple, set)):
                continue
            clean: List[str] = []
            for p in perms:
                ps = str(p or "").strip()
                if ps and ps not in clean:
                    clean.append(ps)
            normalized[key] = clean
        return normalized

    def _get_scratch_dir(self, plugin_id: str) -> Path:
        safe_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(plugin_id or "plugin")).strip("_") or "plugin"
        return (self._sandbox_root / safe_id).resolve()

    def _get_effective_permissions(self, plugin_id: str) -> List[str]:
        manifest = self._manifests.get(plugin_id)
        if manifest is None:
            return []
        src = self._sources.get(plugin_id, {})
        if src.get("builtin") or (not src.get("sandboxed") and not src.get("source_path")):
            return list(manifest.permissions)
        approved = set(self.granted_permissions.get(plugin_id, [])) | set(
            self.granted_permissions.get("*", [])
        )
        return [p for p in manifest.permissions if p in approved]

    def _refresh_permission_metadata(self, plugin_id: str) -> None:
        manifest = self._manifests.get(plugin_id)
        meta = self._metadata.get(plugin_id)
        if manifest is None or meta is None:
            return
        effective = self._get_effective_permissions(plugin_id)
        meta["requested_permissions"] = list(manifest.permissions)
        meta["granted_permissions"] = list(effective)
        meta["denied_permissions"] = [p for p in manifest.permissions if p not in effective]
        meta["permissions"] = list(effective)

    @staticmethod
    def _normalize_sandbox_mode(mode: Any) -> str:
        norm = str(mode or "subprocess").strip().lower()
        if norm not in VALID_SANDBOX_MODES:
            raise ValueError(f"Invalid sandbox_mode '{mode}'. Expected one of {VALID_SANDBOX_MODES}.")
        return norm

    @staticmethod
    def _build_sandbox_env() -> Dict[str, str]:
        """Builds a stripped environment for external plugin subprocesses with zero host secrets."""
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": str(REPO_ROOT),
        }
        if os.name == "nt" and os.environ.get("SYSTEMROOT"):
            # Required on Windows for _overlapped/WinSock initialization in asyncio.
            env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
        return env

    def update_config(self, settings: Dict[str, Any]) -> None:
        if not isinstance(settings, dict):
            return
        cfg = settings.get("plugins", settings) if isinstance(settings.get("plugins"), dict) else settings
        if "enabled" in cfg:
            self.enabled = bool(cfg.get("enabled", True))
        if "plugins_dir" in cfg and cfg.get("plugins_dir"):
            self.plugins_dir = Path(str(cfg["plugins_dir"]))
        if "enabled_plugins" in cfg and isinstance(cfg["enabled_plugins"], list):
            self.enabled_plugins = [str(p).strip() for p in cfg["enabled_plugins"] if str(p).strip()]
        if "hook_timeout_sec" in cfg:
            self.hook_timeout_sec = max(0.1, float(cfg.get("hook_timeout_sec", 5.0) or 5.0))
        if "startup_timeout_sec" in cfg:
            self.startup_timeout_sec = max(0.5, float(cfg.get("startup_timeout_sec", 5.0) or 5.0))
        if "sandbox_mode" in cfg and cfg.get("sandbox_mode") is not None:
            self.sandbox_mode = self._normalize_sandbox_mode(cfg.get("sandbox_mode"))
        if "granted_permissions" in cfg:
            self.granted_permissions = self._normalize_granted_permissions(cfg.get("granted_permissions"))
            for pid in list(self._metadata.keys()):
                self._refresh_permission_metadata(pid)

    def _build_context(self, plugin_id: str) -> PluginContext:
        state_store = self._plugin_states.setdefault(plugin_id, {})
        ctx = PluginContext(
            plugin_id=plugin_id,
            event_bus=self.event_bus,
            speak_cb=self._speak_cb,
            broadcast_cb=self._broadcast_cb,
            state_store=state_store,
        )
        self._contexts[plugin_id] = ctx
        return ctx

    def _rebuild_command_map(self) -> None:
        self._command_map.clear()
        if not self.enabled:
            return
        for plugin_id, manifest in self._manifests.items():
            meta = self._metadata.get(plugin_id, {})
            if not meta.get("loaded") or not meta.get("enabled"):
                continue
            for cmd in manifest.commands:
                norm = PluginManifest._norm_cmd(cmd)
                self._command_map.setdefault(norm, plugin_id)

    async def _emit_plugin_event(self, action: str, plugin_id: str, extra: Optional[Dict[str, Any]] = None) -> None:
        if self.event_bus is None:
            return
        payload = {"action": action, "plugin_id": plugin_id, **(extra or {})}
        try:
            await self.event_bus.publish("plugin.event", payload)
        except Exception as exc:
            print(f"[PluginRegistry] Failed publishing plugin.event: {exc}")

    @staticmethod
    def _extract_plugin_classes(module: Any) -> List[Type[MaybeAIPlugin]]:
        classes: List[Type[MaybeAIPlugin]] = []
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj is MaybeAIPlugin:
                continue
            if issubclass(obj, MaybeAIPlugin) and obj.__module__ == module.__name__:
                classes.append(obj)
        return classes

    @staticmethod
    def _eval_ast_value(node: ast.AST) -> Any:
        if isinstance(node, ast.Name):
            if node.id == "ALLOWED_PLUGIN_PERMISSIONS":
                return list(ALLOWED_PLUGIN_PERMISSIONS)
            if node.id == "DEFAULT_PLUGIN_PERMISSIONS":
                return list(DEFAULT_PLUGIN_PERMISSIONS)
            raise ValueError(f"Unsupported AST name: {node.id}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in ("list", "tuple") and len(node.args) == 1 and not node.keywords:
                inner = PluginRegistry._eval_ast_value(node.args[0])
                return list(inner) if node.func.id == "list" else tuple(inner)
            raise ValueError("Unsupported AST call")
        return ast.literal_eval(node)

    @classmethod
    def _extract_manifest_from_ast(cls, file_path: Path) -> Optional[PluginManifest]:
        """
        Extracts a PluginManifest via static AST inspection without executing module code.
        Returns None if the manifest cannot be statically resolved.
        """
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_path))
        except Exception:
            return None

        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            manifest_call: Optional[ast.Call] = None
            for stmt in node.body:
                val = None
                if isinstance(stmt, ast.Assign):
                    if any(isinstance(t, ast.Name) and t.id == "manifest" for t in stmt.targets):
                        val = stmt.value
                elif isinstance(stmt, ast.AnnAssign):
                    if isinstance(stmt.target, ast.Name) and stmt.target.id == "manifest":
                        val = stmt.value
                if isinstance(val, ast.Call) and (
                    (isinstance(val.func, ast.Name) and val.func.id == "PluginManifest")
                    or (isinstance(val.func, ast.Attribute) and val.func.attr == "PluginManifest")
                ):
                    manifest_call = val
                    break

            if manifest_call is None:
                continue

            try:
                pos_args = [cls._eval_ast_value(a) for a in manifest_call.args]
                kw_args = {
                    kw.arg: cls._eval_ast_value(kw.value)
                    for kw in manifest_call.keywords
                    if kw.arg is not None
                }
                manifest = PluginManifest(*pos_args, **kw_args)
            except Exception:
                return None

            # Mirror MaybeAIPlugin._index_decorated_methods() for @plugin_command / @plugin_event
            for stmt in node.body:
                if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for dec in stmt.decorator_list:
                    if not isinstance(dec, ast.Call):
                        continue
                    dec_name = (
                        dec.func.id
                        if isinstance(dec.func, ast.Name)
                        else (dec.func.attr if isinstance(dec.func, ast.Attribute) else "")
                    )
                    if dec_name == "plugin_command":
                        try:
                            c_args = [cls._eval_ast_value(a) for a in dec.args]
                            c_kw = {
                                kw.arg: cls._eval_ast_value(kw.value)
                                for kw in dec.keywords
                                if kw.arg is not None
                            }
                            raw_cmd = c_args[0] if c_args else c_kw.get("name", "")
                            creator_only = bool(c_args[1] if len(c_args) > 1 else c_kw.get("creator_only", False))
                            norm_cmd = PluginManifest._norm_cmd(str(raw_cmd))
                            if norm_cmd and norm_cmd not in manifest.commands:
                                manifest.commands.append(norm_cmd)
                            if creator_only and norm_cmd and norm_cmd not in manifest.creator_only_commands:
                                manifest.creator_only_commands.append(norm_cmd)
                        except Exception:
                            return None
                    elif dec_name == "plugin_event":
                        try:
                            e_args = [cls._eval_ast_value(a) for a in dec.args]
                            e_kw = {
                                kw.arg: cls._eval_ast_value(kw.value)
                                for kw in dec.keywords
                                if kw.arg is not None
                            }
                            ev = str(e_args[0] if e_args else e_kw.get("event_name", "")).strip()
                            if ev and ev not in manifest.events:
                                manifest.events.append(ev)
                        except Exception:
                            return None

            try:
                manifest.validate()
                return manifest
            except Exception:
                return None

        return None

    def _create_sandbox_client(self, plugin_id: str, source_path: Path) -> _SandboxPluginClient:
        return _SandboxPluginClient(
            plugin_id=plugin_id,
            source_path=source_path,
            scratch_dir=self._get_scratch_dir(plugin_id),
            env=self._build_sandbox_env(),
            permission_provider=lambda: self._get_effective_permissions(plugin_id),
            speak_cb=self._speak_cb,
            broadcast_cb=self._broadcast_cb,
            event_bus_provider=lambda: self.event_bus,
        )

    def _register_sandbox_manifest(
        self,
        manifest: PluginManifest,
        source_path: str,
        auto_enable: Optional[bool] = None,
        sandbox_level: str = SANDBOX_LEVEL_SUBPROCESS_RESTRICTED,
        os_isolation_detail: str = "pending",
    ) -> str:
        manifest.validate()
        plugin_id = manifest.id
        is_enabled = (
            bool(auto_enable)
            if auto_enable is not None
            else (plugin_id in self.enabled_plugins)
        )
        if is_enabled and plugin_id not in self.enabled_plugins:
            self.enabled_plugins.append(plugin_id)

        self._manifests[plugin_id] = manifest
        self._sources[plugin_id] = {
            "builtin": False,
            "sandboxed": True,
            "module_name": None,
            "class_name": None,
            "source_path": source_path,
        }
        effective_perms = self._get_effective_permissions(plugin_id)
        self._metadata[plugin_id] = {
            **manifest.to_dict(),
            "permissions": list(effective_perms),
            "requested_permissions": list(manifest.permissions),
            "granted_permissions": list(effective_perms),
            "denied_permissions": [p for p in manifest.permissions if p not in effective_perms],
            "enabled": is_enabled,
            "loaded": False,
            "builtin": False,
            "sandboxed": True,
            "sandbox_level": sandbox_level,
            "os_isolation_detail": os_isolation_detail,
            "scratch_dir": str(self._get_scratch_dir(plugin_id)),
            "source_path": source_path,
            "error_count": 0,
            "last_error": None,
        }
        return plugin_id

    def _record_blocked_plugin(self, file_path: Path, error: Exception) -> str:
        plugin_id = file_path.stem
        self._sources[plugin_id] = {
            "builtin": False,
            "sandboxed": True,
            "module_name": None,
            "class_name": None,
            "source_path": str(file_path),
        }
        self._metadata[plugin_id] = {
            "id": plugin_id,
            "name": plugin_id,
            "version": "0.0.0",
            "author": "unknown",
            "description": "",
            "commands": [],
            "events": [],
            "creator_only_commands": [],
            "permissions": [],
            "requested_permissions": [],
            "granted_permissions": [],
            "denied_permissions": [],
            "enabled": False,
            "loaded": False,
            "builtin": False,
            "sandboxed": True,
            "sandbox_level": SANDBOX_LEVEL_BLOCKED,
            "os_isolation_detail": "blocked",
            "scratch_dir": str(self._get_scratch_dir(plugin_id)),
            "source_path": str(file_path),
            "error_count": 1,
            "last_error": f"{type(error).__name__}: {error}",
        }
        return plugin_id

    def register_plugin(
        self,
        plugin: MaybeAIPlugin,
        builtin: bool = False,
        source_path: Optional[str] = None,
        module_name: Optional[str] = None,
        auto_enable: Optional[bool] = None,
    ) -> str:
        """Validates and registers an in-process plugin instance without running `on_load` yet."""
        if not builtin and source_path is not None:
            raise PermissionError(
                "In-process execution of external plugins is disallowed; use subprocess sandbox."
            )
        if not isinstance(plugin, MaybeAIPlugin):
            raise TypeError("Plugin must inherit from MaybeAIPlugin.")
        manifest = getattr(plugin, "manifest", None)
        if not isinstance(manifest, PluginManifest):
            raise ValueError("Plugin must define a PluginManifest instance on `.manifest`.")
        manifest.validate()

        plugin_id = manifest.id
        is_enabled = (
            bool(auto_enable)
            if auto_enable is not None
            else (plugin_id in self.enabled_plugins)
        )
        if is_enabled and plugin_id not in self.enabled_plugins:
            self.enabled_plugins.append(plugin_id)

        self._plugins[plugin_id] = plugin
        self._manifests[plugin_id] = manifest
        self._sources[plugin_id] = {
            "builtin": builtin,
            "sandboxed": False,
            "module_name": module_name or plugin.__class__.__module__,
            "class_name": plugin.__class__.__name__,
            "source_path": source_path,
        }
        effective_perms = self._get_effective_permissions(plugin_id)
        self._metadata[plugin_id] = {
            **manifest.to_dict(),
            "permissions": list(effective_perms),
            "requested_permissions": list(manifest.permissions),
            "granted_permissions": list(effective_perms),
            "denied_permissions": [p for p in manifest.permissions if p not in effective_perms],
            "enabled": is_enabled,
            "loaded": False,
            "builtin": builtin,
            "sandboxed": False,
            "sandbox_level": SANDBOX_LEVEL_BUILTIN if builtin else "inprocess",
            "os_isolation_detail": "builtin_trusted" if builtin else "inprocess_legacy",
            "source_path": source_path,
            "error_count": 0,
            "last_error": None,
        }
        self._build_context(plugin_id)
        return plugin_id

    async def _probe_sandbox_manifest(self, file_path: Path) -> Tuple[PluginManifest, _SandboxPluginClient]:
        client = self._create_sandbox_client(plugin_id=file_path.stem, source_path=file_path)
        try:
            await client.start()
            raw_manifest = await asyncio.wait_for(
                client.call("manifest", {}),
                timeout=self.startup_timeout_sec,
            )
            manifest = PluginManifest(**raw_manifest)
            manifest.validate()
            client.plugin_id = manifest.id
            return manifest, client
        except Exception:
            await client.kill_and_cleanup()
            raise

    async def _evict_dead_subprocess(self, plugin_id: str, meta: Optional[Dict[str, Any]] = None) -> None:
        """Evict a dead or crashed sandboxed subprocess client from _subprocesses."""
        client = self._subprocesses.pop(plugin_id, None)
        if client is not None:
            await client.kill_and_cleanup()
        if meta is not None and meta.get("loaded"):
            meta["loaded"] = False
            self._rebuild_command_map()

    async def _load_plugin_instance(self, plugin_id: str) -> bool:
        meta = self._metadata.get(plugin_id)
        src = self._sources.get(plugin_id, {})
        if meta is None:
            return False
        if not self.enabled or not meta.get("enabled"):
            return False
        if meta.get("loaded"):
            return True

        if meta.get("sandboxed"):
            source_path = Path(src["source_path"])
            client = self._subprocesses.get(plugin_id)
            if client is None or not client.is_running:
                if client is not None:
                    await self._evict_dead_subprocess(plugin_id, meta)
                client = self._create_sandbox_client(plugin_id=plugin_id, source_path=source_path)
                self._subprocesses[plugin_id] = client
            try:
                await client.start()
                meta["sandbox_level"] = client.sandbox_level
                meta["os_isolation_detail"] = client.os_isolation_detail
                meta["scratch_dir"] = str(client.scratch_dir)
                state = self._plugin_states.setdefault(plugin_id, {})
                res = await asyncio.wait_for(
                    client.call("on_load", {"state": state}),
                    timeout=self.hook_timeout_sec,
                )
                if isinstance(res, dict) and isinstance(res.get("state"), dict):
                    self._plugin_states[plugin_id] = dict(res["state"])
                meta["loaded"] = True
                meta["last_error"] = None
                self._rebuild_command_map()
                await self._emit_plugin_event("loaded", plugin_id)
                return True
            except Exception as exc:
                await client.kill_and_cleanup()
                self._subprocesses.pop(plugin_id, None)
                meta["loaded"] = False
                meta["sandbox_level"] = SANDBOX_LEVEL_BLOCKED
                meta["error_count"] = int(meta.get("error_count", 0)) + 1
                err_name = getattr(exc, "error_type", type(exc).__name__)
                meta["last_error"] = f"{err_name}: {exc}"
                print(f"[PluginRegistry] on_load error for '{plugin_id}': {meta['last_error']}")
                return False

        if not src.get("builtin") and src.get("source_path"):
            meta["loaded"] = False
            meta["sandbox_level"] = SANDBOX_LEVEL_BLOCKED
            meta["os_isolation_detail"] = "inprocess_blocked"
            meta["error_count"] = int(meta.get("error_count", 0)) + 1
            meta["last_error"] = "PermissionError: In-process execution of external plugins is disabled"
            return False

        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            return False
        ctx = self._build_context(plugin_id)
        try:
            await asyncio.wait_for(plugin.on_load(ctx), timeout=self.hook_timeout_sec)
            meta["loaded"] = True
            meta["last_error"] = None
            self._rebuild_command_map()
            await self._emit_plugin_event("loaded", plugin_id)
            return True
        except Exception as exc:
            meta["loaded"] = False
            meta["error_count"] = int(meta.get("error_count", 0)) + 1
            meta["last_error"] = f"{type(exc).__name__}: {exc}"
            print(f"[PluginRegistry] on_load error for '{plugin_id}': {meta['last_error']}")
            return False

    async def _unload_plugin_instance(self, plugin_id: str) -> None:
        meta = self._metadata.get(plugin_id)
        if meta is None:
            return

        if meta.get("sandboxed"):
            client = self._subprocesses.pop(plugin_id, None)
            if not meta.get("loaded") and client is None:
                return
            try:
                if client is not None and client.is_running and meta.get("loaded"):
                    res = await asyncio.wait_for(
                        client.call("on_unload", {}),
                        timeout=self.hook_timeout_sec,
                    )
                    if isinstance(res, dict) and isinstance(res.get("state"), dict):
                        self._plugin_states[plugin_id] = dict(res["state"])
            except Exception as exc:
                meta["error_count"] = int(meta.get("error_count", 0)) + 1
                err_name = getattr(exc, "error_type", type(exc).__name__)
                meta["last_error"] = f"{err_name}: {exc}"
                print(f"[PluginRegistry] on_unload error for '{plugin_id}': {meta['last_error']}")
            finally:
                if client is not None:
                    await client.graceful_shutdown(timeout=min(self.hook_timeout_sec, 2.0))
                meta["loaded"] = False
                self._rebuild_command_map()
                await self._emit_plugin_event("unloaded", plugin_id)
            return

        plugin = self._plugins.get(plugin_id)
        if plugin is None or not meta.get("loaded"):
            return
        ctx = self._contexts.get(plugin_id) or self._build_context(plugin_id)
        try:
            await asyncio.wait_for(plugin.on_unload(ctx), timeout=self.hook_timeout_sec)
        except Exception as exc:
            meta["error_count"] = int(meta.get("error_count", 0)) + 1
            meta["last_error"] = f"{type(exc).__name__}: {exc}"
            print(f"[PluginRegistry] on_unload error for '{plugin_id}': {meta['last_error']}")
        finally:
            meta["loaded"] = False
            self._rebuild_command_map()
            await self._emit_plugin_event("unloaded", plugin_id)

    async def discover_plugins(self) -> List[str]:
        """
        Discovers built-in plugins in `core/plugins/` and external `.py` plugins in `plugins_dir`.
        Loads any discovered plugins listed in `enabled_plugins` when registry is enabled.
        """
        discovered_ids: List[str] = []

        # 1. Built-in plugins (always fast in-process)
        for mod_name in BUILTIN_MODULES:
            try:
                module = importlib.import_module(mod_name)
                for cls in self._extract_plugin_classes(module):
                    instance = cls()
                    pid = self.register_plugin(
                        instance,
                        builtin=True,
                        module_name=mod_name,
                    )
                    discovered_ids.append(pid)
            except Exception as exc:
                print(f"[PluginRegistry] Failed discovering built-in '{mod_name}': {exc}")

        # 2. External .py plugins in plugins_dir (if present)
        if self.plugins_dir.exists() and self.plugins_dir.is_dir():
            for file_path in sorted(self.plugins_dir.glob("*.py")):
                if file_path.name.startswith("_"):
                    continue
                if self.sandbox_mode == "subprocess":
                    # Prefer static AST manifest extraction to avoid import-time code execution during discovery.
                    ast_manifest = self._extract_manifest_from_ast(file_path)
                    if ast_manifest is not None:
                        pid = self._register_sandbox_manifest(
                            ast_manifest,
                            source_path=str(file_path),
                        )
                        discovered_ids.append(pid)
                        continue
                    try:
                        manifest, client = await self._probe_sandbox_manifest(file_path)
                        pid = self._register_sandbox_manifest(
                            manifest,
                            source_path=str(file_path),
                            sandbox_level=client.sandbox_level,
                            os_isolation_detail=client.os_isolation_detail,
                        )
                        discovered_ids.append(pid)
                        if self.enabled and self._metadata[pid].get("enabled"):
                            self._subprocesses[pid] = client
                        else:
                            await client.graceful_shutdown(timeout=min(self.hook_timeout_sec, 2.0))
                    except Exception as exc:
                        # Never silently fall back to inprocess; mark external plugin as blocked.
                        blocked_pid = self._record_blocked_plugin(file_path, exc)
                        discovered_ids.append(blocked_pid)
                        print(f"[PluginRegistry] Blocked sandboxed plugin '{file_path}': {exc}")
                else:
                    # Disallow inprocess execution for ALL external plugins (SEC-GAP-002).
                    blocked_pid = self._record_blocked_plugin(
                        file_path,
                        PermissionError(
                            "In-process execution of external plugins is disallowed; use 'subprocess' sandbox_mode."
                        ),
                    )
                    discovered_ids.append(blocked_pid)
                    print(f"[PluginRegistry] Blocked external plugin '{file_path}': inprocess mode is disallowed")

        # 3. Load enabled plugins
        if self.enabled:
            for pid in list(self._metadata.keys()):
                if self._metadata[pid].get("enabled"):
                    await self._load_plugin_instance(pid)

        self._rebuild_command_map()
        return discovered_ids

    async def enable_plugin(self, plugin_id: str) -> Dict[str, Any]:
        meta = self._metadata.get(plugin_id)
        if meta is None:
            return {"success": False, "error": f"Unknown plugin '{plugin_id}'."}
        meta["enabled"] = True
        if plugin_id not in self.enabled_plugins:
            self.enabled_plugins.append(plugin_id)
        loaded = await self._load_plugin_instance(plugin_id)
        return {
            "success": loaded or not self.enabled,
            "plugin": dict(meta),
        }

    async def disable_plugin(self, plugin_id: str) -> Dict[str, Any]:
        meta = self._metadata.get(plugin_id)
        if meta is None:
            return {"success": False, "error": f"Unknown plugin '{plugin_id}'."}
        await self._unload_plugin_instance(plugin_id)
        meta["enabled"] = False
        if plugin_id in self.enabled_plugins:
            self.enabled_plugins = [p for p in self.enabled_plugins if p != plugin_id]
        self._rebuild_command_map()
        return {"success": True, "plugin": dict(meta)}

    async def reload_plugin(self, plugin_id: str) -> Dict[str, Any]:
        meta = self._metadata.get(plugin_id)
        src = self._sources.get(plugin_id)
        if meta is None or src is None:
            return {"success": False, "error": f"Unknown plugin '{plugin_id}'."}

        was_enabled = bool(meta.get("enabled", True))
        await self._unload_plugin_instance(plugin_id)

        try:
            if src.get("sandboxed") and src.get("source_path") and self.sandbox_mode == "subprocess":
                file_path = Path(src["source_path"])
                ast_manifest = self._extract_manifest_from_ast(file_path)
                if ast_manifest is not None:
                    self._register_sandbox_manifest(
                        ast_manifest,
                        source_path=str(file_path),
                        auto_enable=was_enabled,
                    )
                else:
                    manifest, client = await self._probe_sandbox_manifest(file_path)
                    self._register_sandbox_manifest(
                        manifest,
                        source_path=str(file_path),
                        auto_enable=was_enabled,
                        sandbox_level=client.sandbox_level,
                        os_isolation_detail=client.os_isolation_detail,
                    )
                    if was_enabled and self.enabled:
                        self._subprocesses[plugin_id] = client
                    else:
                        await client.graceful_shutdown(timeout=min(self.hook_timeout_sec, 2.0))
            elif src.get("source_path"):
                raise PermissionError(
                    "In-process execution of external plugins is disallowed; use 'subprocess' sandbox_mode."
                )
            elif src.get("builtin"):
                module = importlib.reload(importlib.import_module(src["module_name"]))
                cls = getattr(module, src["class_name"])
                new_instance = cls()
                self.register_plugin(
                    new_instance,
                    builtin=True,
                    module_name=src["module_name"],
                    auto_enable=was_enabled,
                )
            else:
                cls = self._plugins[plugin_id].__class__
                new_instance = cls()
                self.register_plugin(
                    new_instance,
                    builtin=bool(src.get("builtin")),
                    module_name=src.get("module_name"),
                    auto_enable=was_enabled,
                )
        except Exception as exc:
            if src.get("sandboxed") or src.get("source_path"):
                meta["sandbox_level"] = SANDBOX_LEVEL_BLOCKED
            meta["error_count"] = int(meta.get("error_count", 0)) + 1
            meta["last_error"] = f"{type(exc).__name__}: {exc}"
            return {"success": False, "error": meta["last_error"], "plugin": dict(meta)}

        if was_enabled and self.enabled:
            ok = await self._load_plugin_instance(plugin_id)
            return {"success": ok, "plugin": dict(self._metadata[plugin_id])}
        return {"success": True, "plugin": dict(self._metadata[plugin_id])}

    async def dispatch_command(
        self,
        text: str,
        user: str = "Viewer",
        is_creator: bool = False,
    ) -> Tuple[bool, Optional[str]]:
        """
        Routes a `!command` to the owning enabled plugin with timeout and exception isolation.
        Returns `(handled: bool, response: Optional[str])`.
        """
        if not self.enabled:
            return False, None
        clean = (text or "").strip()
        if not clean.startswith("!"):
            return False, None

        parts = clean.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1].strip() if len(parts) > 1 else ""

        plugin_id = self._command_map.get(cmd)
        if not plugin_id:
            return False, None

        manifest = self._manifests.get(plugin_id)
        meta = self._metadata.get(plugin_id)
        if manifest is None or meta is None or not meta.get("loaded") or not meta.get("enabled"):
            return False, None

        if cmd in manifest.creator_only_commands and not is_creator:
            return True, "Maaf, command plugin ini khusus untuk Creator saja!"

        if meta.get("sandboxed"):
            client = self._subprocesses.get(plugin_id)
            if client is None or not client.is_running:
                if client is not None:
                    await self._evict_dead_subprocess(plugin_id, meta)
                return False, None
            try:
                res = await asyncio.wait_for(
                    client.call(
                        "on_command",
                        {
                            "cmd": cmd,
                            "args": args,
                            "user": user,
                            "is_creator": is_creator,
                        },
                    ),
                    timeout=self.hook_timeout_sec,
                )
                response = res.get("response") if isinstance(res, dict) else res
                if isinstance(res, dict) and isinstance(res.get("state"), dict):
                    self._plugin_states[plugin_id] = dict(res["state"])
                await self._emit_plugin_event(
                    "command",
                    plugin_id,
                    {"command": cmd, "user": user, "handled": True},
                )
                return True, response
            except asyncio.TimeoutError:
                await self._evict_dead_subprocess(plugin_id, meta)
                meta["error_count"] = int(meta.get("error_count", 0)) + 1
                meta["last_error"] = f"Command '{cmd}' timed out after {self.hook_timeout_sec}s"
                print(f"[PluginRegistry] {meta['last_error']} (plugin={plugin_id})")
                return True, None
            except Exception as exc:
                if not client.is_running:
                    await self._evict_dead_subprocess(plugin_id, meta)
                meta["error_count"] = int(meta.get("error_count", 0)) + 1
                err_name = getattr(exc, "error_type", type(exc).__name__)
                meta["last_error"] = f"{err_name}: {exc}"
                print(f"[PluginRegistry] Command '{cmd}' error in '{plugin_id}': {meta['last_error']}")
                return True, None

        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            return False, None
        ctx = self._contexts.get(plugin_id) or self._build_context(plugin_id)
        try:
            response = await asyncio.wait_for(
                plugin.on_command(cmd, args, user, is_creator, ctx),
                timeout=self.hook_timeout_sec,
            )
            await self._emit_plugin_event(
                "command",
                plugin_id,
                {"command": cmd, "user": user, "handled": True},
            )
            return True, response
        except asyncio.TimeoutError:
            meta["error_count"] = int(meta.get("error_count", 0)) + 1
            meta["last_error"] = f"Command '{cmd}' timed out after {self.hook_timeout_sec}s"
            print(f"[PluginRegistry] {meta['last_error']} (plugin={plugin_id})")
            return True, None
        except Exception as exc:
            meta["error_count"] = int(meta.get("error_count", 0)) + 1
            meta["last_error"] = f"{type(exc).__name__}: {exc}"
            print(f"[PluginRegistry] Command '{cmd}' error in '{plugin_id}': {meta['last_error']}")
            return True, None

    def attach_to_event_bus(self, event_bus: Any) -> None:
        """Subscribes to EventBus events so enabled plugins receive their declared events safely."""
        if event_bus is None:
            return
        if self._bus_attached and self.event_bus is event_bus:
            return
        if self.event_bus is not None and self._bus_attached:
            self.event_bus.unsubscribe("*", self._on_bus_event)
        self.event_bus = event_bus
        for ctx in self._contexts.values():
            ctx.event_bus = event_bus
        self.event_bus.subscribe("*", self._on_bus_event)
        self._bus_attached = True

    async def _on_bus_event(self, event_name: str, payload: Dict[str, Any]) -> None:
        if not self.enabled or event_name == "plugin.event":
            return
        for plugin_id in list(self._metadata.keys()):
            meta = self._metadata.get(plugin_id, {})
            manifest = self._manifests.get(plugin_id)
            if manifest is None or not meta.get("loaded") or not meta.get("enabled"):
                continue
            if "event:sub" not in self._get_effective_permissions(plugin_id):
                continue
            declared = manifest.events
            if event_name not in declared and "*" not in declared:
                continue

            if meta.get("sandboxed"):
                client = self._subprocesses.get(plugin_id)
                if client is None or not client.is_running:
                    if client is not None:
                        await self._evict_dead_subprocess(plugin_id, meta)
                    continue
                try:
                    res = await asyncio.wait_for(
                        client.call(
                            "on_event",
                            {"event_name": event_name, "payload": dict(payload or {})},
                        ),
                        timeout=self.hook_timeout_sec,
                    )
                    if isinstance(res, dict) and isinstance(res.get("state"), dict):
                        self._plugin_states[plugin_id] = dict(res["state"])
                except asyncio.TimeoutError:
                    await self._evict_dead_subprocess(plugin_id, meta)
                    meta["error_count"] = int(meta.get("error_count", 0)) + 1
                    meta["last_error"] = f"Event '{event_name}' timed out after {self.hook_timeout_sec}s"
                    print(f"[PluginRegistry] {meta['last_error']} (plugin={plugin_id})")
                except Exception as exc:
                    if not client.is_running:
                        await self._evict_dead_subprocess(plugin_id, meta)
                    meta["error_count"] = int(meta.get("error_count", 0)) + 1
                    err_name = getattr(exc, "error_type", type(exc).__name__)
                    meta["last_error"] = f"{err_name}: {exc}"
                    print(f"[PluginRegistry] Event '{event_name}' error in '{plugin_id}': {meta['last_error']}")
                continue

            plugin = self._plugins.get(plugin_id)
            if plugin is None:
                continue
            ctx = self._contexts.get(plugin_id) or self._build_context(plugin_id)
            try:
                await asyncio.wait_for(
                    plugin.on_event(event_name, dict(payload or {}), ctx),
                    timeout=self.hook_timeout_sec,
                )
            except asyncio.TimeoutError:
                meta["error_count"] = int(meta.get("error_count", 0)) + 1
                meta["last_error"] = f"Event '{event_name}' timed out after {self.hook_timeout_sec}s"
                print(f"[PluginRegistry] {meta['last_error']} (plugin={plugin_id})")
            except Exception as exc:
                meta["error_count"] = int(meta.get("error_count", 0)) + 1
                meta["last_error"] = f"{type(exc).__name__}: {exc}"
                print(f"[PluginRegistry] Event '{event_name}' error in '{plugin_id}': {meta['last_error']}")

    async def shutdown(self) -> None:
        """Unloads all active plugins, terminates sandboxed subprocesses, and detaches from EventBus."""
        for pid in list(self._metadata.keys()):
            await self._unload_plugin_instance(pid)
        for pid in list(self._subprocesses.keys()):
            client = self._subprocesses.pop(pid, None)
            if client is not None:
                await client.kill_and_cleanup()
        if self.event_bus is not None and self._bus_attached:
            self.event_bus.unsubscribe("*", self._on_bus_event)
            self._bus_attached = False

    def list_plugins(self) -> List[Dict[str, Any]]:
        return [dict(meta) for meta in self._metadata.values()]
