"""Document records and files, owned per user.

SQLite (WAL) on the data volume for dev; Phase 3 moves it to managed Postgres/Mongo. Every read
takes the owner, so another user's document is indistinguishable from a missing one. Files live
under ``<data>/files/<owner>/<document>/v<n>/``; a revision adds a version and never rewrites an
earlier one.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  kind TEXT NOT NULL,
  template TEXT NOT NULL,
  title TEXT NOT NULL,
  conversation_id TEXT,
  created_at REAL NOT NULL,
  expires_at REAL
);
CREATE INDEX IF NOT EXISTS documents_owner ON documents(owner);
CREATE TABLE IF NOT EXISTS versions (
  document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  status TEXT NOT NULL,
  template_version TEXT NOT NULL,
  filename TEXT,
  mime_type TEXT,
  bytes INTEGER,
  sha256 TEXT,
  pages INTEGER,
  checks TEXT NOT NULL DEFAULT '{}',
  error TEXT,
  spec TEXT NOT NULL,
  message_id TEXT,
  duration_ms INTEGER,
  created_at REAL NOT NULL,
  PRIMARY KEY (document_id, version)
);
"""

STATUS_PENDING = "pending"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"


@dataclass
class Version:
    document_id: str
    version: int
    status: str
    template_version: str
    filename: str | None
    mime_type: str | None
    bytes: int | None
    sha256: str | None
    pages: int | None
    checks: dict
    error: str | None
    spec: dict
    duration_ms: int | None
    created_at: float


@dataclass
class Document:
    id: str
    owner: str
    kind: str
    template: str
    title: str
    conversation_id: str | None
    created_at: float
    expires_at: float | None
    versions: list[Version] = field(default_factory=list)

    @property
    def latest(self) -> Version | None:
        return self.versions[-1] if self.versions else None


class Store:
    def __init__(self, data_dir: Path, retention_days: int = 0):
        self.data_dir = data_dir
        self.files_dir = data_dir / "files"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days
        self._lock = threading.Lock()
        self._db = sqlite3.connect(data_dir / "office.db", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # -- paths -------------------------------------------------------------------------------

    def version_dir(self, owner: str, document_id: str, version: int) -> Path:
        path = self.files_dir / owner / document_id / f"v{version}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    # -- writes ------------------------------------------------------------------------------

    def create_document(
        self, *, owner: str, kind: str, template: str, title: str, conversation_id: str | None
    ) -> str:
        document_id = uuid.uuid4().hex
        now = time.time()
        expires = now + self.retention_days * 86400 if self.retention_days else None
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO documents VALUES (?,?,?,?,?,?,?,?)",
                (document_id, owner, kind, template, title, conversation_id, now, expires),
            )
        return document_id

    def add_version(
        self,
        *,
        owner: str,
        document_id: str,
        template_version: str,
        spec: dict,
        message_id: str | None,
    ) -> int:
        with self._lock, self._db:
            owned = self._db.execute(
                "SELECT 1 FROM documents WHERE id=? AND owner=?", (document_id, owner)
            ).fetchone()
            if not owned:
                raise KeyError(document_id)
            row = self._db.execute(
                "SELECT COALESCE(MAX(version),0) AS n FROM versions WHERE document_id=?",
                (document_id,),
            ).fetchone()
            version = int(row["n"]) + 1
            self._db.execute(
                "INSERT INTO versions (document_id, version, status, template_version, spec, "
                "message_id, created_at) VALUES (?,?,?,?,?,?,?)",
                (
                    document_id,
                    version,
                    STATUS_PENDING,
                    template_version,
                    json.dumps(spec),
                    message_id,
                    time.time(),
                ),
            )
        return version

    def complete_version(
        self,
        *,
        document_id: str,
        version: int,
        file_path: Path,
        mime_type: str,
        pages: int | None,
        checks: dict,
        duration_ms: int,
    ) -> None:
        data = file_path.read_bytes()
        with self._lock, self._db:
            self._db.execute(
                "UPDATE versions SET status=?, filename=?, mime_type=?, bytes=?, sha256=?, "
                "pages=?, checks=?, duration_ms=? WHERE document_id=? AND version=?",
                (
                    STATUS_COMPLETE,
                    file_path.name,
                    mime_type,
                    len(data),
                    hashlib.sha256(data).hexdigest(),
                    pages,
                    json.dumps(checks),
                    duration_ms,
                    document_id,
                    version,
                ),
            )

    def fail_version(self, *, document_id: str, version: int, error: str, checks: dict) -> None:
        with self._lock, self._db:
            self._db.execute(
                "UPDATE versions SET status=?, error=?, checks=? WHERE document_id=? AND version=?",
                (STATUS_FAILED, error[:2000], json.dumps(checks), document_id, version),
            )

    # -- reads (always owner-scoped) ---------------------------------------------------------

    def get_document(self, owner: str, document_id: str) -> Document | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM documents WHERE id=? AND owner=?", (document_id, owner)
            ).fetchone()
            if not row:
                return None
            rows = self._db.execute(
                "SELECT * FROM versions WHERE document_id=? ORDER BY version", (document_id,)
            ).fetchall()
        doc = Document(**{k: row[k] for k in row.keys()})
        doc.versions = [
            Version(
                document_id=r["document_id"],
                version=r["version"],
                status=r["status"],
                template_version=r["template_version"],
                filename=r["filename"],
                mime_type=r["mime_type"],
                bytes=r["bytes"],
                sha256=r["sha256"],
                pages=r["pages"],
                checks=json.loads(r["checks"] or "{}"),
                error=r["error"],
                spec=json.loads(r["spec"]),
                duration_ms=r["duration_ms"],
                created_at=r["created_at"],
            )
            for r in rows
        ]
        return doc

    def list_documents(self, owner: str, limit: int = 20) -> list[Document]:
        with self._lock:
            ids = [
                r["id"]
                for r in self._db.execute(
                    "SELECT id FROM documents WHERE owner=? ORDER BY created_at DESC LIMIT ?",
                    (owner, limit),
                ).fetchall()
            ]
        return [doc for doc in (self.get_document(owner, i) for i in ids) if doc]

    def file_path(self, owner: str, document_id: str, version: int, name: str) -> Path | None:
        """Path to a stored artifact of an owned, completed version, or None."""
        doc = self.get_document(owner, document_id)
        if not doc:
            return None
        match = next((v for v in doc.versions if v.version == version), None)
        if not match or match.status != STATUS_COMPLETE:
            return None
        if name == "file":
            name = match.filename or ""
        path = self.files_dir / owner / document_id / f"v{version}" / name
        return path if name and path.is_file() else None

    # -- retention ---------------------------------------------------------------------------

    def purge_expired(self, now: float | None = None) -> int:
        now = now or time.time()
        with self._lock:
            rows = self._db.execute(
                "SELECT id, owner FROM documents WHERE expires_at IS NOT NULL AND expires_at < ?",
                (now,),
            ).fetchall()
            with self._db:
                for r in rows:
                    self._db.execute("DELETE FROM documents WHERE id=?", (r["id"],))
        for r in rows:
            shutil.rmtree(self.files_dir / r["owner"] / r["id"], ignore_errors=True)
        return len(rows)
