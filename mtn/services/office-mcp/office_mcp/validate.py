"""Checks a generated file must pass before it is marked complete and delivered."""

from __future__ import annotations

import zipfile
from pathlib import Path

MIME = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
# The main part each package must contain, and the content type that part must declare.
MAIN_PART = {
    ".docx": ("word/document.xml", "wordprocessingml.document.main+xml"),
    ".pptx": ("ppt/presentation.xml", "presentationml.presentation.main+xml"),
    ".xlsx": ("xl/workbook.xml", "spreadsheetml.sheet.main+xml"),
}


class ValidationFailed(Exception):
    def __init__(self, message: str, checks: dict):
        super().__init__(message)
        self.checks = checks


def check_package(path: Path, max_bytes: int, checks: dict) -> str:
    """Signature, ZIP integrity, content types and size. Returns the MIME type."""
    ext = path.suffix.lower()
    if ext not in MIME:
        raise ValidationFailed(f"unsupported file type {ext}", checks)
    size = path.stat().st_size
    if size > max_bytes:
        raise ValidationFailed(f"the file is {size} bytes, over the {max_bytes} byte limit", checks)
    with path.open("rb") as handle:
        if handle.read(4) != b"PK\x03\x04":
            raise ValidationFailed("the file is not an Office Open XML package", checks)
    checks["signature"] = "ok"
    try:
        with zipfile.ZipFile(path) as package:
            bad = package.testzip()
            if bad:
                raise ValidationFailed(f"corrupt package entry {bad}", checks)
            names = set(package.namelist())
            main, content_type = MAIN_PART[ext]
            types_xml = package.read("[Content_Types].xml").decode("utf-8", errors="replace")
    except zipfile.BadZipFile as exc:
        raise ValidationFailed(f"the package is not a valid ZIP ({exc})", checks) from None
    except KeyError:
        raise ValidationFailed("the package has no [Content_Types].xml", checks) from None
    if main not in names or content_type not in types_xml:
        raise ValidationFailed(f"the package has no {main} main part", checks)
    checks["package"] = "ok"
    checks["bytes"] = size
    return MIME[ext]
