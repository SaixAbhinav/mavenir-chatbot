import zipfile
from pathlib import Path

import pytest
from noc_copilot.acquire import (
    download_url, extract_document, normalise_to_docx, resolve_soffice,
)
from noc_copilot.config import SpecEntry

SPEC = SpecEntry(spec_id="38.331", series="38", title="t", role="r", version="17.5.0")

try:
    resolve_soffice()
    _NO_SOFFICE_REASON = None
except RuntimeError as exc:
    _NO_SOFFICE_REASON = str(exc)

requires_soffice = pytest.mark.skipif(
    _NO_SOFFICE_REASON is not None,
    reason="LibreOffice is a local ingest prerequisite, not present on this machine",
)

def test_download_url_uses_encoded_version():
    assert download_url(SPEC) == (
        "https://www.3gpp.org/ftp/Specs/archive/38_series/38.331/38331-h50.zip"
    )

def test_extract_document_finds_the_word_file(tmp_path):
    zip_path = tmp_path / "s.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("38331-h50.doc", b"payload")
        zf.writestr("notes.txt", b"ignore me")
    out = extract_document(zip_path, tmp_path)
    assert out.name == "38331-h50.doc"
    assert out.read_bytes() == b"payload"

def test_extract_document_rejects_archive_without_word_file(tmp_path):
    zip_path = tmp_path / "s.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("readme.txt", b"nothing here")
    with pytest.raises(ValueError, match="no .doc or .docx"):
        extract_document(zip_path, tmp_path)

def test_extract_document_rejects_ambiguous_payloads(tmp_path):
    """Two Word files, neither matching the archive's own stem: must fail
    loudly rather than silently guessing (e.g. picking a cover sheet)."""
    zip_path = tmp_path / "38331-hh0.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("coversheet.docx", b"cover")
        zf.writestr("changehistory.docx", b"history")
    with pytest.raises(ValueError, match="no unambiguous payload"):
        extract_document(zip_path, tmp_path)

def test_normalise_passes_docx_through_unchanged(tmp_path):
    src = tmp_path / "already.docx"
    src.write_bytes(b"x")
    assert normalise_to_docx(src, tmp_path) == src

@requires_soffice
def test_resolve_soffice_reports_a_usable_path():
    # LibreOffice is a documented local prerequisite; this asserts setup is correct.
    assert resolve_soffice().exists()

@requires_soffice
def test_normalise_converts_a_legacy_format(tmp_path):
    """RTF exercises the same conversion path as legacy .doc without needing a
    binary .doc fixture in the repo."""
    src = tmp_path / "sample.rtf"
    src.write_text(r"{\rtf1\ansi Clause 5.3.5.3 text.\par}", encoding="ascii")
    out = normalise_to_docx(src, tmp_path)
    assert out.suffix == ".docx"
    assert out.exists() and out.stat().st_size > 0
