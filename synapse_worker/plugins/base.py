"""Plugin manifest + registry base (§4.11).

A plugin (capability pack) is provisioned once on the daemon in its own venv/sandbox,
then attached per agent. This module parses ``plugin.toml`` and tracks installed plugins;
the provisioning lifecycle lives in ``plugins/runtime.py`` (added by the plugin unit).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, Optional

from ..errors import ManifestError

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]


@dataclass
class ProvidedMCP:
    name: str
    transport: str = "stdio"
    command: str = ""


@dataclass
class ProvidedTool:
    name: str
    exec: str = ""


@dataclass
class PluginManifest:
    id: str
    name: str
    version: str
    kind: str  # mcp | script | workspace | composite
    platforms: list[str] = field(default_factory=list)
    install: dict[str, Any] = field(default_factory=dict)
    provides_mcp: list[ProvidedMCP] = field(default_factory=list)
    provides_tool: list[ProvidedTool] = field(default_factory=list)
    permissions: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PluginManifest":
        plugin = data.get("plugin", {})
        if not plugin.get("name"):
            raise ManifestError("plugin.toml missing [plugin].name")
        provides = data.get("provides", {})
        mcp = [ProvidedMCP(**m) for m in _as_list(provides.get("mcp"))]
        tools = [ProvidedTool(**t) for t in _as_list(provides.get("tool"))]
        return cls(
            id=plugin.get("id", plugin["name"]),
            name=plugin["name"],
            version=str(plugin.get("version", "0.0.0")),
            kind=plugin.get("kind", "mcp"),
            platforms=plugin.get("platforms", []),
            install=data.get("install", {}),
            provides_mcp=mcp,
            provides_tool=tools,
            permissions=data.get("permissions", {}),
            raw=data,
        )

    @classmethod
    def from_toml(cls, text: str) -> "PluginManifest":
        if tomllib is None:  # pragma: no cover
            raise ManifestError("tomllib unavailable (Python < 3.11)")
        try:
            data = tomllib.loads(text)
        except Exception as exc:  # noqa: BLE001
            raise ManifestError(f"invalid plugin.toml: {exc}") from exc
        return cls.from_dict(data)

    def supports_platform(self, platform: str) -> bool:
        return not self.platforms or platform in self.platforms


def _as_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    return []


@dataclass
class InstalledPlugin:
    manifest: PluginManifest
    status: str = "installing"  # installing | ready | failed
    error: Optional[str] = None


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, InstalledPlugin] = {}

    def add(self, manifest: PluginManifest, status: str = "installing") -> InstalledPlugin:
        rec = InstalledPlugin(manifest=manifest, status=status)
        self._plugins[manifest.name] = rec
        return rec

    def set_status(self, name: str, status: str, error: Optional[str] = None) -> None:
        rec = self._plugins.get(name)
        if rec is not None:
            rec.status = status
            rec.error = error

    def remove(self, name: str) -> None:
        self._plugins.pop(name, None)

    def get(self, name: str) -> Optional[InstalledPlugin]:
        return self._plugins.get(name)

    def all(self) -> list[InstalledPlugin]:
        return list(self._plugins.values())


_registry: PluginRegistry = PluginRegistry()


def get_plugin_registry() -> PluginRegistry:
    return _registry


def reset_plugin_registry() -> None:  # test helper
    global _registry
    _registry = PluginRegistry()
