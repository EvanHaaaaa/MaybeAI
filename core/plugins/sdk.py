import copy
import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional


@dataclass
class PluginManifest:
    """Declarative metadata and capability manifest for a MaybeAI plugin."""

    id: str
    name: str
    version: str = "1.0.0"
    author: str = "MaybeAI"
    description: str = ""
    commands: List[str] = field(default_factory=list)
    events: List[str] = field(default_factory=list)
    creator_only_commands: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.id = str(self.id or "").strip()
        self.name = str(self.name or "").strip()
        self.version = str(self.version or "1.0.0").strip()
        self.author = str(self.author or "MaybeAI").strip()
        self.description = str(self.description or "").strip()
        self.commands = [self._norm_cmd(c) for c in (self.commands or []) if str(c).strip()]
        self.events = [str(e).strip() for e in (self.events or []) if str(e).strip()]
        self.creator_only_commands = [
            self._norm_cmd(c) for c in (self.creator_only_commands or []) if str(c).strip()
        ]

    @staticmethod
    def _norm_cmd(cmd: str) -> str:
        c = str(cmd).strip().lower()
        if c and not c.startswith("!"):
            c = f"!{c}"
        return c

    def validate(self) -> None:
        if not self.id or any(ch.isspace() for ch in self.id):
            raise ValueError(f"Invalid plugin manifest id: '{self.id}'")
        if not self.name:
            raise ValueError(f"Plugin '{self.id}' manifest requires a non-empty 'name'.")
        for cmd in self.commands:
            if not cmd.startswith("!") or len(cmd) < 2:
                raise ValueError(f"Plugin '{self.id}' has invalid command '{cmd}'.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "commands": list(self.commands),
            "events": list(self.events),
            "creator_only_commands": list(self.creator_only_commands),
        }


class PluginContext:
    """
    Sandboxed execution facade provided to plugins.
    Exposes only safe EventBus publishing, speech/broadcast helpers, and per-plugin state
    without leaking raw Orchestrator, Brain, or ConfigManager internals.
    """

    def __init__(
        self,
        plugin_id: str,
        event_bus: Optional[Any] = None,
        speak_cb: Optional[Callable[[str, str], Awaitable[Any]]] = None,
        broadcast_cb: Optional[Callable[[str, Dict[str, Any]], Awaitable[Any]]] = None,
        state_store: Optional[Dict[str, Any]] = None,
    ):
        self.plugin_id = plugin_id
        self.event_bus = event_bus
        self._speak_cb = speak_cb
        self._broadcast_cb = broadcast_cb
        self._state: Dict[str, Any] = state_store if state_store is not None else {}

    async def speak(self, text: str, emotion: str = "neutral") -> None:
        clean_text = str(text or "").strip()
        if not clean_text:
            return
        if self._speak_cb is not None:
            res = self._speak_cb(clean_text, emotion)
            if inspect.isawaitable(res):
                await res
        elif self.event_bus is not None:
            await self.event_bus.publish(
                "plugin.event",
                {
                    "plugin_id": self.plugin_id,
                    "kind": "speak",
                    "text": clean_text,
                    "emotion": emotion,
                },
            )

    async def broadcast(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        payload = dict(data or {})
        if self._broadcast_cb is not None:
            res = self._broadcast_cb(event_type, payload)
            if inspect.isawaitable(res):
                await res
        elif self.event_bus is not None:
            await self.event_bus.publish(
                "plugin.event",
                {
                    "plugin_id": self.plugin_id,
                    "kind": "broadcast",
                    "event_type": event_type,
                    "data": payload,
                },
            )

    def get_plugin_state(self, key: str, default: Any = None) -> Any:
        if key not in self._state:
            return copy.deepcopy(default)
        return copy.deepcopy(self._state[key])

    def set_plugin_state(self, key: str, value: Any) -> None:
        self._state[str(key)] = copy.deepcopy(value)


def plugin_command(name: str, creator_only: bool = False, description: str = "") -> Callable:
    """Decorator marking a `MaybeAIPlugin` method as a chat command handler."""
    norm = PluginManifest._norm_cmd(name)

    def decorator(func: Callable) -> Callable:
        cmds = list(getattr(func, "_plugin_commands", []))
        cmds.append(
            {
                "name": norm,
                "creator_only": bool(creator_only),
                "description": description,
            }
        )
        setattr(func, "_plugin_commands", cmds)
        return func

    return decorator


def plugin_event(event_name: str) -> Callable:
    """Decorator marking a `MaybeAIPlugin` method as an EventBus event handler."""
    ev = str(event_name or "").strip()

    def decorator(func: Callable) -> Callable:
        events = list(getattr(func, "_plugin_events", []))
        if ev and ev not in events:
            events.append(ev)
        setattr(func, "_plugin_events", events)
        return func

    return decorator


class MaybeAIPlugin:
    """Base class for all built-in and external MaybeAI plugins."""

    manifest: PluginManifest = PluginManifest(
        id="base_plugin",
        name="Base Plugin",
        description="Abstract base plugin.",
    )

    def __init__(self) -> None:
        self.manifest = copy.deepcopy(self.manifest)
        self._command_handlers: Dict[str, Tuple[Callable, bool]] = {}
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._index_decorated_methods()

    def _index_decorated_methods(self) -> None:
        for attr_name in dir(self):
            if attr_name.startswith("__"):
                continue
            attr = getattr(self, attr_name, None)
            if not callable(attr):
                continue
            for meta in getattr(attr, "_plugin_commands", []):
                cmd = meta["name"]
                self._command_handlers[cmd] = (attr, bool(meta.get("creator_only", False)))
                if cmd not in self.manifest.commands:
                    self.manifest.commands.append(cmd)
                if meta.get("creator_only") and cmd not in self.manifest.creator_only_commands:
                    self.manifest.creator_only_commands.append(cmd)
            for ev in getattr(attr, "_plugin_events", []):
                self._event_handlers.setdefault(ev, []).append(attr)
                if ev not in self.manifest.events:
                    self.manifest.events.append(ev)

    async def on_load(self, ctx: PluginContext) -> None:
        """Called when the plugin is loaded and enabled."""
        return None

    async def on_unload(self, ctx: PluginContext) -> None:
        """Called when the plugin is disabled, reloaded, or shut down."""
        return None

    async def on_command(
        self,
        cmd: str,
        args: str,
        user: str,
        is_creator: bool,
        ctx: PluginContext,
    ) -> Optional[str]:
        """Handles a registered `!command`. Dispatches `@plugin_command` methods by default."""
        norm_cmd = PluginManifest._norm_cmd(cmd)
        entry = self._command_handlers.get(norm_cmd)
        if entry is None:
            return None
        handler, creator_only = entry
        if creator_only and not is_creator:
            return "Maaf, command ini khusus untuk Creator saja!"
        res = handler(args, user, is_creator, ctx)
        if inspect.isawaitable(res):
            return await res
        return res

    async def on_event(
        self,
        event_name: str,
        payload: Dict[str, Any],
        ctx: PluginContext,
    ) -> None:
        """Handles a subscribed EventBus event. Dispatches `@plugin_event` methods by default."""
        handlers = list(self._event_handlers.get(event_name, ())) + list(
            self._event_handlers.get("*", ())
        )
        for handler in handlers:
            res = handler(event_name, payload, ctx)
            if inspect.isawaitable(res):
                await res
