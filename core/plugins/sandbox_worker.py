"""
Standalone stdio JSON-RPC 2.0 worker for out-of-process sandboxed MaybeAI plugins.

Usage:
    python -m core.plugins.sandbox_worker <plugin_path>
"""

import argparse
import asyncio
import builtins
import importlib.util
import inspect
import io
import json
import os
import socket
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Type

from core.plugins.sdk import MaybeAIPlugin, PluginContext, PluginManifest


_BOUNDARY_GUARD_INSTALLED = False


def apply_os_resource_limits() -> Dict[str, Any]:
    """
    Applies OS-level resource limits inside the worker where supported (POSIX/Linux).
    Returns diagnostic metadata describing applied limits.
    """
    if os.name == "nt":
        # On Windows, memory/process limits are enforced by the host via Job Objects.
        return {"applied": False, "detail": "host_managed_windows"}

    try:
        import resource  # type: ignore
    except ImportError:
        return {"applied": False, "detail": "resource_module_unavailable"}

    applied: List[str] = []
    mem_bytes = 512 * 1024 * 1024
    for limit_name in ("RLIMIT_AS", "RLIMIT_DATA"):
        limit_const = getattr(resource, limit_name, None)
        if limit_const is None:
            continue
        try:
            soft, hard = resource.getrlimit(limit_const)
            target = mem_bytes if hard in (-1, getattr(resource, "RLIM_INFINITY", -1)) else min(mem_bytes, hard)
            if soft == getattr(resource, "RLIM_INFINITY", -1) or soft > target:
                resource.setrlimit(limit_const, (target, hard))
            applied.append(limit_name.lower())
            break
        except (OSError, ValueError):
            continue

    nofile_const = getattr(resource, "RLIMIT_NOFILE", None)
    if nofile_const is not None:
        try:
            soft, hard = resource.getrlimit(nofile_const)
            target = 128 if hard in (-1, getattr(resource, "RLIM_INFINITY", -1)) else min(128, hard)
            if soft == getattr(resource, "RLIM_INFINITY", -1) or soft > target:
                resource.setrlimit(nofile_const, (target, hard))
            applied.append("rlimit_nofile")
        except (OSError, ValueError):
            pass

    return {
        "applied": bool(applied),
        "detail": ",".join(applied) if applied else "rlimit_unavailable",
    }


def _resolve_safe_path(raw_path: Any) -> Path:
    if isinstance(raw_path, bytes):
        raw_path = os.fsdecode(raw_path)
    p = Path(os.fspath(raw_path))
    try:
        return p.resolve()
    except Exception:
        return Path(os.path.abspath(str(p)))


def _is_under_dir(target: Path, parent: Path) -> bool:
    return target == parent or parent in target.parents


def install_boundary_guards(
    scratch_dir: Path,
    repo_root: Path,
    permissions: Iterable[str] = (),
) -> None:
    """
    Installs worker-side filesystem and network boundary guards before importing plugin code.
    Blocks reading `.env`, `config/settings.json` (`config/`), `data/`, writes outside `scratch_dir`,
    and unauthorized outbound sockets unless explicitly permitted by host-approved capabilities.
    """
    global _BOUNDARY_GUARD_INSTALLED
    if _BOUNDARY_GUARD_INSTALLED:
        return
    _BOUNDARY_GUARD_INSTALLED = True

    granted: Set[str] = {str(p).strip() for p in permissions if str(p).strip()}
    allow_fs_read = "fs:read" in granted
    allow_fs_write = "fs:write" in granted
    allow_net_outbound = "net:outbound" in granted or "network:outbound" in granted
    allow_sys_exec = "sys:exec" in granted

    resolved_scratch = _resolve_safe_path(scratch_dir)
    resolved_repo = _resolve_safe_path(repo_root)
    blocked_config_dir = _resolve_safe_path(resolved_repo / "config")
    blocked_data_dir = _resolve_safe_path(resolved_repo / "data")

    def _check_fs_access(file_arg: Any, is_write: bool) -> None:
        if isinstance(file_arg, int):
            return
        resolved = _resolve_safe_path(file_arg)
        name_lower = resolved.name.lower()
        parts_lower = [part.lower() for part in resolved.parts]

        # Always block .env files unless fs:read is explicitly granted
        is_env_file = name_lower == ".env" or name_lower.startswith(".env.")
        is_config_target = _is_under_dir(resolved, blocked_config_dir) or (
            len(parts_lower) >= 2 and parts_lower[-2] == "config" and name_lower == "settings.json"
        )
        is_data_target = _is_under_dir(resolved, blocked_data_dir) or (
            "data" in parts_lower and not _is_under_dir(resolved, resolved_scratch)
        )

        if not allow_fs_read and (is_env_file or is_config_target or is_data_target):
            raise PermissionError(
                f"Sandbox boundary: access to '{file_arg}' denied (requires host-approved capability)"
            )

        if is_write and not allow_fs_write and not _is_under_dir(resolved, resolved_scratch):
            raise PermissionError(
                f"Sandbox boundary: write access outside scratch dir '{file_arg}' denied"
            )

    orig_open = builtins.open
    orig_os_open = os.open

    def _guarded_open(file, mode="r", *args, **kwargs):
        mode_str = str(mode or "r")
        is_write = any(ch in mode_str for ch in ("w", "a", "x", "+"))
        _check_fs_access(file, is_write=is_write)
        return orig_open(file, mode, *args, **kwargs)

    def _guarded_os_open(path, flags, *args, **kwargs):
        write_mask = getattr(os, "O_WRONLY", 1) | getattr(os, "O_RDWR", 2) | getattr(os, "O_CREAT", 0) | getattr(os, "O_APPEND", 0)
        is_write = bool(flags & write_mask)
        _check_fs_access(path, is_write=is_write)
        return orig_os_open(path, flags, *args, **kwargs)

    builtins.open = _guarded_open  # type: ignore[assignment]
    io.open = _guarded_open  # type: ignore[assignment]
    os.open = _guarded_os_open  # type: ignore[assignment]

    if not allow_sys_exec:
        _blocked_roots = ("ctypes", "_ctypes", "subprocess", "_winapi", "winreg")

        class _BlockedModuleFinder:
            """sys.meta_path blocker preventing untrusted plugins from importing native/exec modules."""

            def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> Any:  # noqa: ARG002
                if fullname in _blocked_roots or fullname.startswith(tuple(f"{r}." for r in _blocked_roots)):
                    raise PermissionError(
                        f"Sandbox boundary: import of '{fullname}' denied (requires 'sys:exec' capability)"
                    )
                return None

        # Evict any pre-imported blocked modules (e.g., _winapi/subprocess imported by asyncio)
        # so subsequent plugin imports hit _BlockedModuleFinder instead of sys.modules cache.
        for mod_name in list(sys.modules):
            if mod_name in _blocked_roots or mod_name.startswith(tuple(f"{r}." for r in _blocked_roots)):
                sys.modules.pop(mod_name, None)

        sys.meta_path.insert(0, _BlockedModuleFinder())

        def _deny_os_system(*args, **kwargs):  # noqa: ARG001
            raise PermissionError(
                "Sandbox boundary: os.system denied (requires 'sys:exec' capability)"
            )

        def _deny_os_popen(*args, **kwargs):  # noqa: ARG001
            raise PermissionError(
                "Sandbox boundary: os.popen denied (requires 'sys:exec' capability)"
            )

        os.system = _deny_os_system  # type: ignore[assignment]
        os.popen = _deny_os_popen  # type: ignore[assignment]
        if hasattr(os, "startfile"):
            def _deny_os_startfile(*args, **kwargs):  # noqa: ARG001
                raise PermissionError(
                    "Sandbox boundary: os.startfile denied (requires 'sys:exec' capability)"
                )

            os.startfile = _deny_os_startfile  # type: ignore[assignment]

    if not allow_net_outbound:
        orig_connect = socket.socket.connect
        orig_connect_ex = socket.socket.connect_ex
        orig_create_connection = socket.create_connection
        orig_socketpair = socket.socketpair
        _pair_state = threading.local()

        def _guarded_socketpair(*args, **kwargs):
            _pair_state.active = True
            try:
                return orig_socketpair(*args, **kwargs)
            finally:
                _pair_state.active = False

        def _deny_connect(self, address):
            if getattr(_pair_state, "active", False):
                return orig_connect(self, address)
            raise PermissionError(
                "Sandbox boundary: outbound socket connection denied (requires 'net:outbound' capability)"
            )

        def _deny_connect_ex(self, address):
            if getattr(_pair_state, "active", False):
                return orig_connect_ex(self, address)
            raise PermissionError(
                "Sandbox boundary: outbound socket connection denied (requires 'net:outbound' capability)"
            )

        def _deny_create_connection(address, *args, **kwargs):  # noqa: ARG001
            raise PermissionError(
                "Sandbox boundary: outbound socket connection denied (requires 'net:outbound' capability)"
            )

        socket.socketpair = _guarded_socketpair  # type: ignore[assignment]
        socket.socket.connect = _deny_connect  # type: ignore[method-assign]
        socket.socket.connect_ex = _deny_connect_ex  # type: ignore[method-assign]
        socket.create_connection = _deny_create_connection  # type: ignore[assignment]


class _SandboxedEventBusProxy:
    """Routes `ctx.event_bus.publish(...)` calls from the worker back to the host via JSON-RPC."""

    def __init__(self, rpc_call) -> None:
        self._rpc_call = rpc_call

    async def publish(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> Any:
        return await self._rpc_call(
            "event_bus.publish",
            {"event_type": str(event_type), "data": dict(data or {})},
        )


def load_plugin_from_path(plugin_path: Path) -> MaybeAIPlugin:
    """Loads and instantiates the first `MaybeAIPlugin` subclass found in `plugin_path`."""
    resolved = plugin_path.resolve()
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(f"Plugin file not found: {resolved}")

    mod_name = f"maybeai_ext_plugin_{resolved.stem}"
    spec = importlib.util.spec_from_file_location(mod_name, str(resolved))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module spec for '{resolved}'")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    classes: List[Type[MaybeAIPlugin]] = []
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if obj is MaybeAIPlugin:
            continue
        if issubclass(obj, MaybeAIPlugin) and obj.__module__ == module.__name__:
            classes.append(obj)

    if not classes:
        raise ValueError(f"No MaybeAIPlugin subclass found in '{resolved}'")

    instance = classes[0]()
    if not isinstance(getattr(instance, "manifest", None), PluginManifest):
        raise ValueError(f"Plugin in '{resolved}' must define a PluginManifest on `.manifest`")
    instance.manifest.validate()
    return instance


class SandboxWorker:
    """Bidirectional newline-delimited JSON-RPC 2.0 worker over stdio."""

    def __init__(self, plugin: MaybeAIPlugin, rpc_in: Any, rpc_out: Any) -> None:
        self.plugin = plugin
        self.rpc_in = rpc_in
        self.rpc_out = rpc_out
        self._write_lock = threading.Lock()
        self._pending: Dict[str, asyncio.Future] = {}
        self._cb_seq = 0
        self._loaded = False
        self._stop_event: Optional[asyncio.Event] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        self.ctx = PluginContext(
            plugin_id=plugin.manifest.id,
            event_bus=_SandboxedEventBusProxy(self.call_host),
            speak_cb=self._speak_cb,
            broadcast_cb=self._broadcast_cb,
            state_store={},
        )

    def _send_json(self, payload: Dict[str, Any]) -> None:
        line = json.dumps(payload, ensure_ascii=False, default=str)
        with self._write_lock:
            self.rpc_out.write(line + "\n")
            self.rpc_out.flush()

    async def call_host(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        assert self._loop is not None
        self._cb_seq += 1
        req_id = f"w-{self._cb_seq}"
        fut: asyncio.Future = self._loop.create_future()
        self._pending[req_id] = fut
        self._send_json(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": method,
                "params": params or {},
            }
        )
        return await fut

    async def _speak_cb(self, text: str, emotion: str = "neutral") -> Any:
        return await self.call_host("ctx.speak", {"text": text, "emotion": emotion})

    async def _broadcast_cb(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> Any:
        return await self.call_host(
            "ctx.broadcast",
            {"event_type": event_type, "data": dict(data or {})},
        )

    async def _dispatch_method(self, method: str, params: Dict[str, Any]) -> Any:
        if method == "manifest":
            self.plugin.manifest.validate()
            return self.plugin.manifest.to_dict()

        if method == "on_load":
            initial_state = params.get("state")
            if isinstance(initial_state, dict):
                self.ctx._state = dict(initial_state)
            await self.plugin.on_load(self.ctx)
            self._loaded = True
            return {"ok": True, "state": dict(self.ctx._state)}

        if method == "on_command":
            cmd = str(params.get("cmd", ""))
            args = str(params.get("args", ""))
            user = str(params.get("user", "Viewer"))
            is_creator = bool(params.get("is_creator", False))
            response = await self.plugin.on_command(cmd, args, user, is_creator, self.ctx)
            return {"response": response, "state": dict(self.ctx._state)}

        if method == "on_event":
            event_name = str(params.get("event_name", ""))
            payload = params.get("payload")
            if not isinstance(payload, dict):
                payload = {}
            await self.plugin.on_event(event_name, payload, self.ctx)
            return {"ok": True, "state": dict(self.ctx._state)}

        if method == "on_unload":
            if self._loaded:
                await self.plugin.on_unload(self.ctx)
                self._loaded = False
            return {"ok": True, "state": dict(self.ctx._state)}

        if method == "shutdown":
            if self._loaded:
                try:
                    await self.plugin.on_unload(self.ctx)
                finally:
                    self._loaded = False
            if self._stop_event is not None:
                self._stop_event.set()
            return {"ok": True}

        raise KeyError(f"Unknown RPC method '{method}'")

    async def _handle_incoming_request(self, msg: Dict[str, Any]) -> None:
        req_id = msg.get("id")
        method = str(msg.get("method", ""))
        params = msg.get("params")
        if not isinstance(params, dict):
            params = {}

        try:
            result = await self._dispatch_method(method, params)
            if req_id is not None:
                self._send_json({"jsonrpc": "2.0", "id": req_id, "result": result})
        except KeyError as exc:
            if req_id is not None:
                self._send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32601, "message": str(exc)},
                    }
                )
        except Exception as exc:
            if req_id is not None:
                self._send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32000,
                            "message": str(exc),
                            "data": {"error_type": type(exc).__name__},
                        },
                    }
                )

    def _on_line(self, line: str) -> None:
        raw = line.strip()
        if not raw:
            return
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        if not isinstance(msg, dict):
            return

        if "method" in msg:
            asyncio.create_task(self._handle_incoming_request(msg))
            return

        if "id" in msg:
            req_id = str(msg["id"])
            fut = self._pending.pop(req_id, None)
            if fut is None or fut.done():
                return
            if "error" in msg and msg["error"] is not None:
                err = msg["error"]
                err_msg = err.get("message", "Host RPC error") if isinstance(err, dict) else str(err)
                code = err.get("code", -32000) if isinstance(err, dict) else -32000
                if code == -32003:
                    fut.set_exception(PermissionError(err_msg))
                else:
                    fut.set_exception(RuntimeError(err_msg))
            else:
                fut.set_result(msg.get("result"))

    def _stdin_reader_thread(self) -> None:
        assert self._loop is not None
        try:
            while True:
                line = self.rpc_in.readline()
                if not line:
                    break
                self._loop.call_soon_threadsafe(self._on_line, line)
        finally:
            if self._stop_event is not None and not self._loop.is_closed():
                self._loop.call_soon_threadsafe(self._stop_event.set)

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        reader = threading.Thread(target=self._stdin_reader_thread, daemon=True)
        reader.start()
        await self._stop_event.wait()
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.cancel()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="MaybeAI sandboxed plugin JSON-RPC 2.0 worker")
    parser.add_argument("plugin_path", help="Path to external MaybeAI plugin .py file")
    parser.add_argument("--scratch-dir", default="", help="Isolated per-plugin scratch working directory")
    parser.add_argument("--repo-root", default="", help="Host repository root for boundary checks")
    parser.add_argument("--permissions", default="", help="Comma-separated host-approved capabilities")
    parser.add_argument("--bwrap-active", action="store_true", help="Indicates host launched worker inside bwrap")
    args = parser.parse_args(argv)

    scratch_dir = Path(args.scratch_dir).resolve() if args.scratch_dir else Path.cwd().resolve()
    scratch_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chdir(str(scratch_dir))
    except OSError:
        pass

    repo_root = (
        Path(args.repo_root).resolve()
        if args.repo_root
        else Path(__file__).resolve().parents[2]
    )
    granted_perms = [p.strip() for p in str(args.permissions or "").split(",") if p.strip()]

    # Apply OS resource limits and boundary guards BEFORE importing any plugin code.
    _limit_info = apply_os_resource_limits()
    install_boundary_guards(
        scratch_dir=scratch_dir,
        repo_root=repo_root,
        permissions=granted_perms,
    )

    # Preserve real stdout for JSON-RPC 2.0 frames; redirect plugin print() calls to stderr.
    rpc_out = sys.stdout
    rpc_in = sys.stdin
    if hasattr(rpc_out, "reconfigure"):
        rpc_out.reconfigure(encoding="utf-8")
    if hasattr(rpc_in, "reconfigure"):
        rpc_in.reconfigure(encoding="utf-8")
    sys.stdout = sys.stderr

    plugin = load_plugin_from_path(Path(args.plugin_path))
    worker = SandboxWorker(plugin=plugin, rpc_in=rpc_in, rpc_out=rpc_out)
    asyncio.run(worker.run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
