"""Template catalogue: ``<templates>/<kind>/<name>/<version>/{manifest.json,template.*}``.

Templates are mounted read-only. Each manifest pins its template file's SHA-256; a file that does
not match is refused, so a tampered or half-copied template never produces a document.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

KINDS = ("word", "powerpoint", "excel")
_VERSION = re.compile(r"^v(\d+)\.(\d+)$")


class TemplateError(Exception):
    pass


@dataclass(frozen=True)
class Template:
    kind: str
    name: str
    version: str
    path: Path
    manifest: dict

    @property
    def title(self) -> str:
        return self.manifest.get("title", self.name)


def _version_key(folder: Path) -> tuple[int, int]:
    match = _VERSION.match(folder.name)
    return (int(match.group(1)), int(match.group(2))) if match else (-1, -1)


def available(root: Path, kind: str) -> dict[str, list[str]]:
    """Template names of a kind and their versions, newest last."""
    base = root / kind
    if not base.is_dir():
        return {}
    result = {}
    for folder in sorted(p for p in base.iterdir() if p.is_dir()):
        versions = sorted(
            (v for v in folder.iterdir() if v.is_dir() and _VERSION.match(v.name)), key=_version_key
        )
        if versions:
            result[folder.name] = [v.name for v in versions]
    return result


def load(root: Path, kind: str, name: str, version: str | None = None) -> Template:
    if kind not in KINDS:
        raise TemplateError(f"unknown template kind '{kind}'")
    versions = available(root, kind).get(name)
    if not versions:
        raise TemplateError(f"unknown {kind} template '{name}'")
    chosen = version or versions[-1]
    if chosen not in versions:
        raise TemplateError(f"{kind} template '{name}' has no version {chosen}")
    folder = root / kind / name / chosen
    manifest = json.loads((folder / "manifest.json").read_text())
    path = folder / manifest["file"]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != manifest.get("sha256"):
        raise TemplateError(f"{kind} template '{name}' {chosen} failed its integrity check")
    return Template(kind=kind, name=name, version=chosen, path=path, manifest=manifest)
