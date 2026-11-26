"""
MaybeAI Plugin CLI (`maybeai plugin init|test|pack`).

Usage:
    python -m core.plugins.cli init <id> [--dir plugins]
    python -m core.plugins.cli test <path>
    python -m core.plugins.cli pack <path> [--out dist]
"""

import argparse
import asyncio
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import List, Optional

from core.plugins.registry import PluginRegistry, _SandboxPluginClient
from core.plugins.sdk import PluginManifest


_PLUGIN_TEMPLATE = '''from core.plugins.sdk import MaybeAIPlugin, PluginContext, PluginManifest, plugin_command


class {class_name}(MaybeAIPlugin):
    """Scaffolded MaybeAI plugin '{plugin_id}'."""

    manifest = PluginManifest(
        id="{plugin_id}",
        name="{display_name}",
        version="1.0.0",
        description="Custom MaybeAI plugin '{plugin_id}'.",
        commands=["!{cmd_name}"],
        permissions=["chat:read", "event:sub"],
    )

    @plugin_command("!{cmd_name}")
    async def handle_{cmd_func}(
        self,
        args: str,
        user: str,
        is_creator: bool,
        ctx: PluginContext,
    ) -> str:
        suffix = f" {{args}}" if args else ""
        return f"[{plugin_id}] Halo {{user}}!{{suffix}}"
'''

_README_TEMPLATE = """# {display_name} (`{plugin_id}`)

Scaffolded with `maybeai plugin init {plugin_id}`.

## Files
- `{plugin_id}.py`: Plugin implementation (`MaybeAIPlugin` subclass).

## Permissions
Declared in `manifest.permissions` (default: `["chat:read", "event:sub"]`).
Allowed values: `chat:read`, `tts:speak`, `event:sub`, `event:pub`, `state:rw`.

## Testing & Packaging
```bash
python -m core.plugins.cli test {plugin_file}
python -m core.plugins.cli pack {plugin_file} --out dist
```
"""


def _to_class_name(plugin_id: str) -> str:
    parts = [p for p in re.split(r"[^a-zA-Z0-9]+", plugin_id) if p]
    base = "".join(p[:1].upper() + p[1:] for p in parts) or "Custom"
    if not base.endswith("Plugin"):
        base += "Plugin"
    if base[0].isdigit():
        base = "Plugin" + base
    return base


def _to_display_name(plugin_id: str) -> str:
    parts = [p for p in re.split(r"[^a-zA-Z0-9]+", plugin_id) if p]
    return " ".join(p[:1].upper() + p[1:] for p in parts) or plugin_id


def cmd_init(plugin_id: str, target_dir: Path, force: bool = False) -> int:
    clean_id = str(plugin_id or "").strip()
    if not clean_id or not re.fullmatch(r"[a-zA-Z0-9_-]+", clean_id):
        print(
            f"[ERROR] Invalid plugin id '{plugin_id}'. Use letters, digits, '_' or '-'.",
            file=sys.stderr,
        )
        return 1

    target_dir.mkdir(parents=True, exist_ok=True)
    plugin_file = target_dir / f"{clean_id}.py"
    readme_file = target_dir / "README.md"

    if plugin_file.exists() and not force:
        print(f"[ERROR] Plugin file already exists: {plugin_file}", file=sys.stderr)
        return 1

    cmd_slug = re.sub(r"[^a-zA-Z0-9]+", "", clean_id.lower()) or "ping"
    class_name = _to_class_name(clean_id)
    display_name = _to_display_name(clean_id)

    plugin_file.write_text(
        _PLUGIN_TEMPLATE.format(
            class_name=class_name,
            plugin_id=clean_id,
            display_name=display_name,
            cmd_name=cmd_slug,
            cmd_func=cmd_slug,
        ),
        encoding="utf-8",
    )
    readme_file.write_text(
        _README_TEMPLATE.format(
            display_name=display_name,
            plugin_id=clean_id,
            plugin_file=plugin_file.as_posix(),
        ),
        encoding="utf-8",
    )
    print(f"Created {plugin_file}")
    print(f"Created {readme_file}")
    return 0


async def _probe_and_test_plugin(plugin_path: Path, timeout_sec: float = 5.0) -> PluginManifest:
    resolved = plugin_path.resolve()
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(f"Plugin file not found: {resolved}")

    client = _SandboxPluginClient(
        plugin_id=resolved.stem,
        source_path=resolved,
        env=PluginRegistry._build_sandbox_env(),
        permission_provider=lambda: [],
    )
    try:
        await client.start()
        raw_manifest = await asyncio.wait_for(client.call("manifest", {}), timeout=timeout_sec)
        manifest = PluginManifest(**raw_manifest)
        manifest.validate()
        client.plugin_id = manifest.id
        client._permission_provider = lambda: list(manifest.permissions)

        await asyncio.wait_for(client.call("on_load", {"state": {}}), timeout=timeout_sec)

        if manifest.commands:
            first_cmd = manifest.commands[0]
            res = await asyncio.wait_for(
                client.call(
                    "on_command",
                    {
                        "cmd": first_cmd,
                        "args": "test",
                        "user": "CLITester",
                        "is_creator": True,
                    },
                ),
                timeout=timeout_sec,
            )
            if not isinstance(res, dict) or "response" not in res:
                raise RuntimeError(f"Unexpected on_command result for {first_cmd}: {res}")

        await asyncio.wait_for(client.call("on_unload", {}), timeout=timeout_sec)
        await client.graceful_shutdown(timeout=min(timeout_sec, 2.0))
        return manifest
    except Exception:
        await client.kill_and_cleanup()
        raise


async def _probe_manifest_only(plugin_path: Path, timeout_sec: float = 5.0) -> PluginManifest:
    resolved = plugin_path.resolve()
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(f"Plugin file not found: {resolved}")

    client = _SandboxPluginClient(
        plugin_id=resolved.stem,
        source_path=resolved,
        env=PluginRegistry._build_sandbox_env(),
        permission_provider=lambda: [],
    )
    try:
        await client.start()
        raw_manifest = await asyncio.wait_for(client.call("manifest", {}), timeout=timeout_sec)
        manifest = PluginManifest(**raw_manifest)
        manifest.validate()
        await client.graceful_shutdown(timeout=min(timeout_sec, 2.0))
        return manifest
    except Exception:
        await client.kill_and_cleanup()
        raise


def cmd_test(plugin_path: Path, timeout_sec: float = 5.0) -> int:
    try:
        manifest = asyncio.run(_probe_and_test_plugin(plugin_path, timeout_sec=timeout_sec))
        print(
            f"[PASS] {manifest.id} v{manifest.version} "
            f"(commands={manifest.commands}, permissions={manifest.permissions})"
        )
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def cmd_pack(plugin_path: Path, out_dir: Path, timeout_sec: float = 5.0) -> int:
    try:
        resolved = plugin_path.resolve()
        manifest = asyncio.run(_probe_manifest_only(resolved, timeout_sec=timeout_sec))
        out_dir.mkdir(parents=True, exist_ok=True)
        zip_path = out_dir / f"{manifest.id}-{manifest.version}.zip"

        plugin_bytes = resolved.read_bytes()
        manifest_bytes = (
            json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False) + "\n"
        ).encode("utf-8")

        entries = [
            (resolved.name, plugin_bytes),
            ("manifest.json", manifest_bytes),
        ]
        checksum_lines = [
            f"{hashlib.sha256(data).hexdigest()}  {name}" for name, data in entries
        ]
        sums_bytes = ("\n".join(checksum_lines) + "\n").encode("utf-8")

        with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, data in entries:
                zf.writestr(name, data)
            zf.writestr("SHA256SUMS.txt", sums_bytes)

        print(f"Packed {zip_path}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="maybeai plugin",
        description="MaybeAI Plugin SDK CLI (init, test, pack)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Scaffold a new plugin .py and README.md")
    p_init.add_argument("id", help="Plugin identifier (e.g. my_plugin)")
    p_init.add_argument("--dir", default="plugins", help="Target directory (default: plugins)")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing plugin file")

    p_test = sub.add_parser("test", help="Test a plugin in the sandboxed subprocess")
    p_test.add_argument("path", help="Path to the plugin .py file")
    p_test.add_argument("--timeout", type=float, default=5.0, help="RPC timeout in seconds")

    p_pack = sub.add_parser("pack", help="Package a plugin into a distributable .zip bundle")
    p_pack.add_argument("path", help="Path to the plugin .py file")
    p_pack.add_argument("--out", default="dist", help="Output directory (default: dist)")
    p_pack.add_argument("--timeout", type=float, default=5.0, help="RPC timeout in seconds")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    if args_list and args_list[0] == "plugin":
        args_list = args_list[1:]

    parser = build_parser()
    parsed = parser.parse_args(args_list)

    if parsed.command == "init":
        return cmd_init(parsed.id, Path(parsed.dir), force=bool(parsed.force))
    if parsed.command == "test":
        return cmd_test(Path(parsed.path), timeout_sec=float(parsed.timeout))
    if parsed.command == "pack":
        return cmd_pack(Path(parsed.path), Path(parsed.out), timeout_sec=float(parsed.timeout))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
