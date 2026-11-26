import asyncio
import importlib
import importlib.util
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Type

from core.plugins.sdk import MaybeAIPlugin, PluginContext, PluginManifest


BUILTIN_MODULES: Tuple[str, ...] = ("core.plugins.word_chain",)
REPO_ROOT: Path = Path(__file__).resolve().parents[2]
VALID_SANDBOX_MODES: Tuple[str, ...] = ("subprocess", "inprocess")


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
        speak_cb: Optional[Callable[[str, str], Awaitable[Any]]] = None,
        broadcast_cb: Optional[Callable[[str, Dict[str, Any]], Awaitable[Any]]] = None,
        event_bus_provider: Optional[Callable[[], Any]] = None,
    ) -> None:
        self.plugin_id = plugin_id
        self.source_path = Path(source_path).resolve()
        self.env = dict(env)
        self._permission_provider = permission_provider
        self._speak_cb = speak_cb
        self._broadcast_cb = broadcast_cb
        self._event_bus_provider = event_bus_provider

        self.proc: Optional[asyncio.subprocess.Process] = None
        self._pending: Dict[str, asyncio.Future] = {}
        self._req_seq = 0
        self._write_lock = asyncio.Lock()
        self._reader_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None

    @property
    def is_running(self) -> bool:
        return self.proc is not None and self.proc.returncode is None

    async def start(self) -> None:
        if self.is_running:
            return
        self.proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "core.plugins.sandbox_worker",
            str(self.source_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self.env,
            cwd=str(REPO_ROOT),
        )
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
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(EOFError(f"Sandbox worker '{self.plugin_id}' exited"))
            self._pending.clear()

    async def _stderr_drain_loop(self) -> None:
        assert self.proc is not None and self.proc.stderr is not None
        try:
            while True:
                line = await self.proc.stderr.readline()
                if not line:
                    break
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
        self.event_bus = event_bus
        self._speak_cb = speak_cb
        self._broadcast_cb = broadcast_cb

        if settings:
            self.update_config(settings)

        self._plugins: Dict[str, MaybeAIPlugin] = {}
        self._manifests: Dict[str, PluginManifest] = {}
        self._subprocesses: Dict[str, _SandboxPluginClient] = {}
        self._contexts: Dict[str, PluginContext] = {}
        self._plugin_states: Dict[str, Dict[str, Any]] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self._sources: Dict[str, Dict[str, Any]] = {}
        self._command_map: Dict[str, str] = {}
        self._bus_attached: bool = False

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

    def _create_sandbox_client(self, plugin_id: str, source_path: Path) -> _SandboxPluginClient:
        return _SandboxPluginClient(
            plugin_id=plugin_id,
            source_path=source_path,
            env=self._build_sandbox_env(),
            permission_provider=lambda: list(
                self._manifests.get(plugin_id).permissions
                if plugin_id in self._manifests
                else ()
            ),
            speak_cb=self._speak_cb,
            broadcast_cb=self._broadcast_cb,
            event_bus_provider=lambda: self.event_bus,
        )

    def _register_sandbox_manifest(
        self,
        manifest: PluginManifest,
        source_path: str,
        auto_enable: Optional[bool] = None,
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
        self._metadata[plugin_id] = {
            **manifest.to_dict(),
            "enabled": is_enabled,
            "loaded": False,
            "builtin": False,
            "sandboxed": True,
            "source_path": source_path,
            "error_count": 0,
            "last_error": None,
        }
        self._sources[plugin_id] = {
            "builtin": False,
            "sandboxed": True,
            "module_name": None,
            "class_name": None,
            "source_path": source_path,
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
        self._metadata[plugin_id] = {
            **manifest.to_dict(),
            "enabled": is_enabled,
            "loaded": False,
            "builtin": builtin,
            "sandboxed": False,
            "source_path": source_path,
            "error_count": 0,
            "last_error": None,
        }
        self._sources[plugin_id] = {
            "builtin": builtin,
            "sandboxed": False,
            "module_name": module_name or plugin.__class__.__module__,
            "class_name": plugin.__class__.__name__,
            "source_path": source_path,
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
                meta["error_count"] = int(meta.get("error_count", 0)) + 1
                err_name = getattr(exc, "error_type", type(exc).__name__)
                meta["last_error"] = f"{err_name}: {exc}"
                print(f"[PluginRegistry] on_load error for '{plugin_id}': {meta['last_error']}")
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
                    try:
                        manifest, client = await self._probe_sandbox_manifest(file_path)
                        pid = self._register_sandbox_manifest(
                            manifest,
                            source_path=str(file_path),
                        )
                        discovered_ids.append(pid)
                        if self.enabled and self._metadata[pid].get("enabled"):
                            self._subprocesses[pid] = client
                        else:
                            await client.graceful_shutdown(timeout=min(self.hook_timeout_sec, 2.0))
                    except Exception as exc:
                        print(f"[PluginRegistry] Failed discovering sandboxed plugin '{file_path}': {exc}")
                else:
                    mod_name = f"maybeai_ext_plugin_{file_path.stem}"
                    try:
                        spec = importlib.util.spec_from_file_location(mod_name, str(file_path))
                        if spec is None or spec.loader is None:
                            continue
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        for cls in self._extract_plugin_classes(module):
                            instance = cls()
                            pid = self.register_plugin(
                                instance,
                                builtin=False,
                                source_path=str(file_path),
                                module_name=mod_name,
                            )
                            discovered_ids.append(pid)
                    except Exception as exc:
                        print(f"[PluginRegistry] Failed loading external plugin '{file_path}': {exc}")

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
            if src.get("sandboxed") and src.get("source_path"):
                file_path = Path(src["source_path"])
                manifest, client = await self._probe_sandbox_manifest(file_path)
                self._register_sandbox_manifest(
                    manifest,
                    source_path=str(file_path),
                    auto_enable=was_enabled,
                )
                if was_enabled and self.enabled:
                    self._subprocesses[plugin_id] = client
                else:
                    await client.graceful_shutdown(timeout=min(self.hook_timeout_sec, 2.0))
            elif src.get("source_path"):
                file_path = Path(src["source_path"])
                mod_name = src["module_name"]
                spec = importlib.util.spec_from_file_location(mod_name, str(file_path))
                if spec is None or spec.loader is None:
                    raise ImportError(f"Cannot load spec for '{file_path}'")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                cls = getattr(module, src["class_name"])
                new_instance = cls()
                self.register_plugin(
                    new_instance,
                    builtin=False,
                    source_path=str(file_path),
                    module_name=mod_name,
                    auto_enable=was_enabled,
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
            if "event:sub" not in manifest.permissions:
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
