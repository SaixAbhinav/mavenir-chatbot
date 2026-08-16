"""Download 3GPP archives and normalise their payload to .docx.

python-docx reads only OOXML .docx. 3GPP archives contain either .doc or
.docx depending on the Specification, so everything is normalised through
headless LibreOffice before parsing.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import requests

from .config import SpecEntry
from .versions import encode_version

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; noc-copilot-ingest/1.0)"}
_DEFAULT_SOFFICE = Path(r"C:\Program Files\LibreOffice\program\soffice.exe")


def download_url(spec: SpecEntry) -> str:
    if spec.version is None:
        raise ValueError(f"{spec.spec_id} has no pinned version; run discover_versions.py")
    stem = spec.spec_id.replace(".", "")
    code = encode_version(spec.version)
    return (
        f"https://www.3gpp.org/ftp/Specs/archive/"
        f"{spec.series}_series/{spec.spec_id}/{stem}-{code}.zip"
    )


def download_spec(spec: SpecEntry, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    url = download_url(spec)
    out = dest / url.rsplit("/", 1)[-1]
    if out.exists() and zipfile.is_zipfile(out):
        return out
    response = requests.get(url, headers=HEADERS, timeout=300)
    response.raise_for_status()
    out.write_bytes(response.content)
    return out


def extract_document(zip_path: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith((".doc", ".docx"))]
        if not names:
            raise ValueError(f"{zip_path.name} contains no .doc or .docx payload")
        if len(names) == 1:
            name = names[0]
        else:
            # Multiple Word payloads: disambiguate by preferring the one whose
            # stem matches the archive's own stem (e.g. 38331-hh0.zip ->
            # 38331-hh0.docx). A cover sheet or change-history file alongside
            # the real document must never be silently picked.
            archive_stem = zip_path.stem.lower()
            matches = [n for n in names if Path(n).stem.lower() == archive_stem]
            if len(matches) != 1:
                raise ValueError(
                    f"{zip_path.name} has no unambiguous payload matching its own "
                    f"stem {archive_stem!r} (candidates: {names})"
                )
            name = matches[0]
        out = dest / Path(name).name
        with zf.open(name) as src, out.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    return out


def resolve_soffice() -> Path:
    env = os.environ.get("LIBREOFFICE_PATH")
    if env and Path(env).exists():
        return Path(env)
    found = shutil.which("soffice") or shutil.which("soffice.exe")
    if found:
        return Path(found)
    if _DEFAULT_SOFFICE.exists():
        return _DEFAULT_SOFFICE
    raise RuntimeError(
        "LibreOffice not found. It is a local ingest prerequisite — see README "
        "'Development setup'. Set LIBREOFFICE_PATH if it is installed elsewhere."
    )


def normalise_to_docx(path: Path, dest: Path) -> Path:
    if path.suffix.lower() == ".docx":
        return path
    dest.mkdir(parents=True, exist_ok=True)
    expected = dest / (path.stem + ".docx")
    subprocess.run(
        [
            str(resolve_soffice()), "--headless", "--convert-to", "docx",
            "--outdir", str(dest), str(path),
        ],
        capture_output=True,
        timeout=600,
        check=False,
    )
    # Success is judged by the output file, not by stderr: headless LibreOffice
    # emits a benign "Could not find platform independent libraries" warning.
    if not expected.exists():
        raise RuntimeError(f"LibreOffice did not produce {expected}")
    return expected
