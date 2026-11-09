"""Excel insights E1: owner-scoped, read-only access to LibreChat uploads."""

import os
import zipfile
from pathlib import Path

import pytest

from office_mcp.errors import ToolError
from office_mcp.files import InsightLimits, LocalUploadsSource, clean_filename

ALICE = "a" * 24
BOB = "b" * 24


def _xlsx(path: Path, extra: dict | None = None) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/workbook.xml", "<workbook/>")
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return path


@pytest.fixture
def uploads(tmp_path):
    for user in (ALICE, BOB):
        (tmp_path / user).mkdir()
    _xlsx(tmp_path / ALICE / "1111aaaa-0000-4000-8000-000000000001__sales.xlsx")
    (tmp_path / ALICE / "2222bbbb-0000-4000-8000-000000000002__team.csv").write_text("a,b\n1,2\n")
    _xlsx(tmp_path / BOB / "3333cccc-0000-4000-8000-000000000003__secret.xlsx")
    return tmp_path


def source(root, **limits):
    return LocalUploadsSource(root, InsightLimits(**limits))


def test_finds_the_owners_file_by_its_name(uploads):
    found = source(uploads).open_for(ALICE, "sales.xlsx")
    assert found.name == "sales.xlsx" and found.suffix == ".xlsx" and found.path.parent.name == ALICE
    assert source(uploads).open_for(ALICE, "team.csv").suffix == ".csv"


def test_another_users_file_is_not_found(uploads):
    with pytest.raises(ToolError, match="No uploaded file named 'secret.xlsx' was found for you"):
        source(uploads).open_for(ALICE, "secret.xlsx")


@pytest.mark.parametrize("name", ["../" + BOB + "/x__secret.xlsx", "/etc/passwd", "..", "a\\b.xlsx", "x\x00.xlsx", ""])
def test_paths_and_odd_names_are_refused(uploads, name):
    with pytest.raises(ToolError):
        source(uploads).open_for(ALICE, name)


@pytest.mark.parametrize("owner", ["", "nobody", "../" + BOB, "A" * 24])
def test_unknown_or_malformed_owner_is_refused(uploads, owner):
    with pytest.raises(ToolError):
        source(uploads).open_for(owner, "sales.xlsx")


def test_a_link_to_another_users_file_is_never_followed(uploads):
    os.symlink(uploads / BOB / "3333cccc-0000-4000-8000-000000000003__secret.xlsx",
               uploads / ALICE / "4444dddd-0000-4000-8000-000000000004__linked.xlsx")
    with pytest.raises(ToolError, match="No uploaded file named 'linked.xlsx'"):
        source(uploads).open_for(ALICE, "linked.xlsx")


def test_the_newest_upload_with_the_same_name_wins(uploads):
    newer = _xlsx(uploads / ALICE / "5555eeee-0000-4000-8000-000000000005__sales.xlsx")
    old = uploads / ALICE / "1111aaaa-0000-4000-8000-000000000001__sales.xlsx"
    os.utime(old, (1_000_000, 1_000_000))
    assert source(uploads).open_for(ALICE, "sales.xlsx").path == newer.resolve()


def test_only_xlsx_and_csv_are_accepted(uploads):
    (uploads / ALICE / "6666ffff-0000-4000-8000-000000000006__notes.docx").write_bytes(b"PK")
    with pytest.raises(ToolError, match="not a spreadsheet"):
        source(uploads).open_for(ALICE, "notes.docx")


def test_size_limit(uploads):
    (uploads / ALICE / "7777aaaa-0000-4000-8000-000000000007__big.csv").write_text("x," * 2000)
    with pytest.raises(ToolError, match="the limit is"):
        source(uploads, max_bytes=1024).open_for(ALICE, "big.csv")


def test_empty_file(uploads):
    (uploads / ALICE / "8888aaaa-0000-4000-8000-000000000008__empty.csv").write_text("")
    with pytest.raises(ToolError, match="is empty"):
        source(uploads).open_for(ALICE, "empty.csv")


def test_archive_that_expands_too_far_is_refused(uploads):
    _xlsx(uploads / ALICE / "9999aaaa-0000-4000-8000-000000000009__bomb.xlsx", {"xl/big.xml": "0" * 3_000_000})
    with pytest.raises(ToolError, match="too large to read safely"):
        source(uploads, max_uncompressed_bytes=1_000_000).open_for(ALICE, "bomb.xlsx")


def test_renamed_non_workbook_and_password_protected_files(uploads):
    (uploads / ALICE / "aaaa1111-0000-4000-8000-00000000000a__fake.xlsx").write_text("not a zip")
    with pytest.raises(ToolError, match="not a valid Excel workbook"):
        source(uploads).open_for(ALICE, "fake.xlsx")
    (uploads / ALICE / "bbbb1111-0000-4000-8000-00000000000b__locked.xlsx").write_bytes(
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 600)
    with pytest.raises(ToolError, match="password-protected"):
        source(uploads).open_for(ALICE, "locked.xlsx")
    with zipfile.ZipFile(uploads / ALICE / "cccc1111-0000-4000-8000-00000000000c__other.xlsx", "w") as z:
        z.writestr("readme.txt", "hello")
    with pytest.raises(ToolError, match="not a valid Excel workbook"):
        source(uploads).open_for(ALICE, "other.xlsx")


def test_clean_filename_strips_quotes():
    assert clean_filename(' "sales.xlsx" ') == "sales.xlsx"
