"""Discover published versions per Specification and pin one common Release.

Run once, on day 1. Writes the chosen release and per-spec versions back into
config/specs.yaml. Versions are never guessed — they come from the archive.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from noc_copilot.config import load_specs  # noqa: E402
from noc_copilot.versions import decode_version, release_of  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
SPECS_YAML = REPO / "config" / "specs.yaml"
# 3gpp.org rejects default user agents with HTTP 403.
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; noc-copilot-ingest/1.0)"}


def archive_url(series: str, spec_id: str) -> str:
    return f"https://www.3gpp.org/ftp/Specs/archive/{series}_series/{spec_id}/"


def parse_listing(html: str, spec_id: str) -> list[str]:
    """Return versions present in a directory listing, newest first."""
    stem = spec_id.replace(".", "")
    codes = re.findall(rf"{stem}-([0-9a-z]{{3}})\.zip", html, flags=re.IGNORECASE)
    versions = {decode_version(code) for code in codes}
    return sorted(
        versions,
        key=lambda v: tuple(int(p) for p in v.split(".")),
        reverse=True,
    )


def choose_common_release(available: dict[str, list[str]]) -> int:
    """Newest release for which every Specification has a published version."""
    release_sets = [
        {release_of(v) for v in versions} for versions in available.values()
    ]
    shared = set.intersection(*release_sets) if release_sets else set()
    if not shared:
        raise ValueError(f"No release is common to all specs: {available}")
    return max(shared)


def newest_in_release(versions: list[str], release: int) -> str:
    return next(v for v in versions if release_of(v) == release)


def main() -> None:
    corpus = load_specs(SPECS_YAML)
    available: dict[str, list[str]] = {}
    for spec in corpus.specs:
        url = archive_url(spec.series, spec.spec_id)
        try:
            response = requests.get(url, headers=HEADERS, timeout=60)
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise SystemExit(
                f"Could not reach {url} ({exc}). "
                "config/specs.yaml has been left unchanged."
            ) from exc
        versions = parse_listing(response.text, spec.spec_id)
        if not versions:
            raise SystemExit(f"No versions found for {spec.spec_id} at {url}")
        available[spec.spec_id] = versions
        print(f"{spec.spec_id}: {len(versions)} versions, newest {versions[0]}")

    release = choose_common_release(available)
    print(f"\nPinning Release {release}")

    raw = yaml.safe_load(SPECS_YAML.read_text(encoding="utf-8"))
    # CorpusConfig.release is typed str | None, so store the release as a string.
    raw["release"] = str(release)
    for entry in raw["specs"]:
        entry["version"] = newest_in_release(available[entry["spec_id"]], release)
        print(f"  {entry['spec_id']} -> v{entry['version']}")
    SPECS_YAML.write_text(
        yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
