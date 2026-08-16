import requests
import pytest

import scripts.discover_versions as discover_versions
from scripts.discover_versions import archive_url, choose_common_release, parse_listing

LISTING = """
<html><body>
<a href="/ftp/Specs/archive/38_series/38.331/38331-h50.zip">38331-h50.zip</a>
<a href="/ftp/Specs/archive/38_series/38.331/38331-i10.zip">38331-i10.zip</a>
<a href="/ftp/Specs/archive/38_series/38.331/38331-g80.zip">38331-g80.zip</a>
<a href="/ftp/Specs/archive/38_series/38.331/readme.txt">readme.txt</a>
</body></html>
"""


def test_archive_url_strips_the_dot():
    assert archive_url("38", "38.331") == (
        "https://www.3gpp.org/ftp/Specs/archive/38_series/38.331/"
    )


def test_parse_listing_returns_versions_newest_first():
    assert parse_listing(LISTING, "38.331") == ["18.1.0", "17.5.0", "16.8.0"]


def test_parse_listing_ignores_non_matching_files():
    assert "readme" not in " ".join(parse_listing(LISTING, "38.331"))


def test_parse_listing_empty_when_no_match():
    assert parse_listing(LISTING, "28.552") == []


def test_choose_common_release_picks_newest_shared():
    available = {
        "38.331": ["18.1.0", "17.5.0"],
        "28.552": ["17.9.0", "16.9.0"],
        "38.321": ["18.0.0", "17.5.0"],
    }
    assert choose_common_release(available) == 17


def test_choose_common_release_raises_when_none_shared():
    available = {"a": ["18.1.0"], "b": ["16.9.0"]}
    with pytest.raises(ValueError, match="No release is common"):
        choose_common_release(available)


def test_main_exits_cleanly_on_network_failure(monkeypatch):
    """A connection error (not just a bad HTTP status) must not traceback,
    must name the failing URL, and must say config/specs.yaml is untouched."""
    original_text = discover_versions.SPECS_YAML.read_text(encoding="utf-8")

    def raise_connection_error(*_args, **_kwargs):
        raise requests.exceptions.ConnectionError("simulated network failure")

    monkeypatch.setattr(requests, "get", raise_connection_error)

    with pytest.raises(SystemExit) as excinfo:
        discover_versions.main()

    message = str(excinfo.value)
    assert "3gpp.org" in message
    assert "config/specs.yaml has been left unchanged" in message
    assert discover_versions.SPECS_YAML.read_text(encoding="utf-8") == original_text
