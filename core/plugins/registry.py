import asyncio
import importlib
import importlib.util
import inspect
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Type

from core.plugins.sdk import MaybeAIPlugin, PluginContext, PluginManifest


BUILTIN_MODULES: Tuple[str, ...] = ("core.plugins.word_chain",)


class PluginRegistry:
    """
    Manages discovery, manifest validation, lifecycle, EventBus integration,
    timeout enforcement, and exception isolation for built-in and external plugins.
    """

    def __init__(
        self,
        plugins_dir: str = "plugins",
        enabled_plugins: Optional[List[str]] = None,
        hook_timeout_sec: float = 5.0,
        enabled: bool = True,
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
        self.event_bus = event_bus
        self._speak_cb = speak_cb
        self._broadcast_cb = broadcast_cb

        if settings:
            self.update_config(settings)

        self._plugins: Dict[str, MaybeAIPlugin] = {}
        self._contexts: Dict[str, PluginContext] = {}
        self._plugin_states: Dict[str, Dict[str, Any]] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self._sources: Dict[str, Dict[str, Any]] = {}
        self._command_map: Dict[str, str] = {}
        self._bus_attached: bool = False

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
        for plugin_id, plugin in self._plugins.items():
            meta = self._metadata.get(plugin_id, {})
            if not meta.get("loaded") or not meta.get("enabled"):
                continue
            for cmd in plugin.manifest.commands:
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

    def register_plugin(
        self,
        plugin: MaybeAIPlugin,
        builtin: bool = False,
        source_path: Optional[str] = None,
        module_name: Optional[str] = None,
        auto_enable: Optional[bool] = None,
    ) -> str:
        """Validates and registers a plugin instance without running `on_load` yet."""
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
        self._metadata[plugin_id] = {
            **manifest.to_dict(),
            "enabled": is_enabled,
            "loaded": False,
            "builtin": builtin,
            "source_path": source_path,
            "error_count": 0,
            "last_error": None,
        }
        self._sources[plugin_id] = {
            "builtin": builtin,
            "module_name": module_name or plugin.__class__.__module__,
            "class_name": plugin.__class__.__name__,
            "source_path": source_path,
        }
        self._build_context(plugin_id)
        return plugin_id

    async def _load_plugin_instance(self, plugin_id: str) -> bool:
        plugin = self._plugins.get(plugin_id)
        meta = self._metadata.get(plugin_id)
        if plugin is None or meta is None:
            return False
        if not self.enabled or not meta.get("enabled"):
            return False
        if meta.get("loaded"):
            return True

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
        plugin = self._plugins.get(plugin_id)
        meta = self._metadata.get(plugin_id)
        if plugin is None or meta is None or not meta.get("loaded"):
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

        # 1. Built-in plugins
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
            for pid in list(self._plugins.keys()):
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
            if src.get("source_path"):
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
                # In-memory registered plugin class
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

        plugin = self._plugins.get(plugin_id)
        meta = self._metadata.get(plugin_id)
        if plugin is None or meta is None or not meta.get("loaded") or not meta.get("enabled"):
            return False, None

        if cmd in plugin.manifest.creator_only_commands and not is_creator:
            return True, "Maaf, command plugin ini khusus untuk Creator saja!"

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
        for plugin_id, plugin in list(self._plugins.items()):
            meta = self._metadata.get(plugin_id, {})
            if not meta.get("loaded") or not meta.get("enabled"):
                continue
            declared = plugin.manifest.events
            if event_name not in declared and "*" not in declared:
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
        """Unloads all active plugins and detaches from EventBus."""
        for pid in list(self._plugins.keys()):
            await self._unload_plugin_instance(pid)
        if self.event_bus is not None and self._bus_attached:
            self.event_bus.unsubscribe("*", self._on_bus_event)
            self._bus_attached = False

    def list_plugins(self) -> List[Dict[str, Any]]:
        return [dict(meta) for meta in self._metadata.values()]
