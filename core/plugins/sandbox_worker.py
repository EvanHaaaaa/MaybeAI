"""
Standalone stdio JSON-RPC 2.0 worker for out-of-process sandboxed MaybeAI plugins.

Usage:
    python -m core.plugins.sandbox_worker <plugin_path>
"""

import argparse
import asyncio
import importlib.util
import inspect
import json
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from core.plugins.sdk import MaybeAIPlugin, PluginContext, PluginManifest


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
    args = parser.parse_args(argv)

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
