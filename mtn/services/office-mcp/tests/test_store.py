import time

from .conftest import ALICE, BOB


def _make(store, owner=ALICE):
    doc_id = store.create_document(
        owner=owner, kind="word", template="proposal", title="T", conversation_id=None
    )
    return doc_id


def test_documents_are_owner_scoped(store):
    doc_id = _make(store)
    assert store.get_document(ALICE, doc_id) is not None
    assert store.get_document(BOB, doc_id) is None
    assert store.list_documents(BOB) == []


def test_versions_increment_and_keep_history(store, tmp_path):
    doc_id = _make(store)
    for expected in (1, 2):
        v = store.add_version(
            owner=ALICE, document_id=doc_id, template_version="v0.1", spec={"n": expected}, message_id=None
        )
        assert v == expected
        out = store.version_dir(ALICE, doc_id, v) / f"doc-v{v}.docx"
        out.write_bytes(b"PK" + bytes([v]))
        store.complete_version(
            document_id=doc_id, version=v, file_path=out, mime_type="x", pages=1, checks={}, duration_ms=1
        )
    doc = store.get_document(ALICE, doc_id)
    assert [v.version for v in doc.versions] == [1, 2]
    assert store.file_path(ALICE, doc_id, 1, "file").read_bytes() == b"PK\x01"
    assert store.file_path(BOB, doc_id, 1, "file") is None


def test_other_user_cannot_add_a_version(store):
    doc_id = _make(store)
    try:
        store.add_version(owner=BOB, document_id=doc_id, template_version="v0.1", spec={}, message_id=None)
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError")


def test_retention_purges_expired_documents(settings):
    from office_mcp.store import Store

    s = Store(settings.data_dir / "r", retention_days=1)
    doc_id = s.create_document(owner=ALICE, kind="word", template="p", title="T", conversation_id=None)
    folder = s.version_dir(ALICE, doc_id, 1)
    assert s.purge_expired(now=time.time()) == 0
    assert s.purge_expired(now=time.time() + 2 * 86400) == 1
    assert s.get_document(ALICE, doc_id) is None
    assert not folder.exists()
    s.close()
