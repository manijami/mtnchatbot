"""Uploaded files a person attached in LibreChat, read-only and owner-scoped (Excel insights).

Two implementations of ``FileSource``:

- ``LocalUploadsSource`` (option A, dev): LibreChat's local uploads folder mounted read-only.
  LibreChat stores each upload as ``<uploads>/<user id>/<file_id>__<original name>``. A lookup
  only ever looks inside the calling user's own folder (the user id comes from
  ``X-MTN-User-Id``, set by LibreChat), so another user's file is simply "not found".
- Option B (required before production, core deviation #3): an owner-checked fetch through
  LibreChat, so S3/Azure storage works. It implements the same interface; the tools do not change.

Every opened file passes the same checks: allowed type, size, and (for .xlsx) the expanded size
of the archive, before any parser sees it.
"""

from __future__ import annotations

import os
import re
import zipfile
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .errors import ToolError

ALLOWED_SUFFIXES = (".xlsx", ".csv")
_USER_ID = re.compile(r"^[a-f0-9]{24}$")
# A LibreChat file id prefix: uuid-like, before the "__" separator.
_STORED_NAME = re.compile(r"^[A-Za-z0-9-]{8,64}__(?P<name>.+)$")
_MAX_NAME_LENGTH = 255


@dataclass(frozen=True)
class InsightLimits:
    max_bytes: int = 15 * 1024 * 1024
    max_uncompressed_bytes: int = 200 * 1024 * 1024
    max_zip_entries: int = 2000
    max_sheets: int = 10
    max_columns: int = 100
    max_rows: int = 100_000
    timeout_s: int = 20
    max_analyses: int = 8


@dataclass(frozen=True)
class SourceFile:
    """A located upload: the name the person knows, where it is, its type and size."""

    name: str
    path: Path
    suffix: str
    size: int


class FileSource(Protocol):
    def open_for(self, owner_id: str, filename: str) -> SourceFile: ...

    def list_for(self, owner_id: str, limit: int = 5) -> list[dict]: ...


def clean_filename(filename: str) -> str:
    """The plain file name the model refers to; anything path-like is refused."""
    name = (filename or "").strip().strip('"').strip("'")
    if not name or len(name) > _MAX_NAME_LENGTH:
        raise ToolError("Give the name of the uploaded file, for example 'sales.xlsx'.")
    if "/" in name or "\\" in name or "\x00" in name or name in (".", "..") or name.startswith(".."):
        raise ToolError("Give only the file's name, not a path, for example 'sales.xlsx'.")
    return name


def check_type_and_size(name: str, path: Path, limits: InsightLimits) -> SourceFile:
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ToolError(
            f"'{name}' is not a spreadsheet this tool can read. Upload an Excel workbook (.xlsx) or a CSV file."
        )
    size = path.stat().st_size
    if size == 0:
        raise ToolError(f"'{name}' is empty.")
    if size > limits.max_bytes:
        raise ToolError(
            f"'{name}' is {size / 1_048_576:.1f} MB; the limit is {limits.max_bytes / 1_048_576:.0f} MB."
        )
    if suffix == ".xlsx":
        _check_xlsx_archive(name, path, limits)
    return SourceFile(name=name, path=path, suffix=suffix, size=size)


def _check_xlsx_archive(name: str, path: Path, limits: InsightLimits) -> None:
    """Refuses archives that are not real workbooks or that expand far beyond their size."""
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            names = {entry.filename for entry in entries}
            if "EncryptedPackage" in names or "EncryptionInfo" in names:
                raise ToolError(f"'{name}' is password-protected. Remove the password and upload it again.")
            if "[Content_Types].xml" not in names or not any(n.startswith("xl/") for n in names):
                raise ToolError(f"'{name}' is not a valid Excel workbook (.xlsx).")
            if len(entries) > limits.max_zip_entries:
                raise ToolError(f"'{name}' has too many parts to read safely.")
            expanded = sum(entry.file_size for entry in entries)
            if expanded > limits.max_uncompressed_bytes:
                raise ToolError(f"'{name}' expands to more than {limits.max_uncompressed_bytes // 1_048_576} MB; it is too large to read safely.")
    except zipfile.BadZipFile as exc:
        # Password-protected workbooks are OLE files, not zip archives.
        with path.open("rb") as handle:
            if handle.read(8) == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
                raise ToolError(f"'{name}' is password-protected or an old .xls file. Save it as .xlsx without a password and upload it again.") from exc
        raise ToolError(f"'{name}' is not a valid Excel workbook (.xlsx).") from exc


class LocalUploadsSource:
    """Option A: LibreChat's local uploads folder, mounted read-only."""

    def __init__(self, root: Path, limits: InsightLimits):
        self.root = root.resolve()
        self.limits = limits

    def open_for(self, owner_id: str, filename: str) -> SourceFile:
        if not _USER_ID.match(owner_id or ""):
            raise ToolError("The signed-in user could not be identified.")
        name = clean_filename(filename)
        owner_dir = (self.root / owner_id).resolve()
        if owner_dir.parent != self.root or not owner_dir.is_dir():
            raise self._not_found(name)
        matches = []
        with os.scandir(owner_dir) as entries:
            for entry in entries:
                stored = _STORED_NAME.match(entry.name)
                if not stored or stored.group("name") != name or not entry.is_file(follow_symlinks=False):
                    continue
                path = Path(entry.path).resolve()
                if path.parent != owner_dir:  # a link pointing elsewhere is never followed
                    continue
                matches.append((entry.stat(follow_symlinks=False).st_mtime, path))
        if not matches:
            raise self._not_found(name)
        newest = max(matches)[1]  # the most recent upload with that name
        return check_type_and_size(name, newest, self.limits)

    def list_for(self, owner_id: str, limit: int = 5) -> list[dict]:
        """The caller's own spreadsheet uploads, newest first (name, size, upload time)."""
        if not _USER_ID.match(owner_id or ""):
            raise ToolError("The signed-in user could not be identified.")
        owner_dir = (self.root / owner_id).resolve()
        if owner_dir.parent != self.root or not owner_dir.is_dir():
            return []
        found = []
        with os.scandir(owner_dir) as entries:
            for entry in entries:
                stored = _STORED_NAME.match(entry.name)
                if not stored or not entry.is_file(follow_symlinks=False):
                    continue
                name = stored.group("name")
                if Path(name).suffix.lower() not in ALLOWED_SUFFIXES:
                    continue
                info = entry.stat(follow_symlinks=False)
                found.append((info.st_mtime, name, info.st_size))
        found.sort(reverse=True)
        seen, result = set(), []
        for mtime, name, size in found:
            if name in seen:
                continue  # the newest upload of a name is the one a lookup uses
            seen.add(name)
            result.append({"file": name, "size_kb": max(1, round(size / 1024)),
                           "uploaded": datetime.fromtimestamp(mtime).isoformat(timespec="minutes")})
            if len(result) == limit:
                break
        return result

    @staticmethod
    def _not_found(name: str) -> ToolError:
        return ToolError(
            f"No uploaded file named '{name}' was found for you. Attach it to the chat and give its exact name."
        )
