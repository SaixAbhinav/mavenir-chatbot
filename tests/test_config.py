from pathlib import Path
import pytest
from noc_copilot.config import load_specs, load_settings

REPO = Path(__file__).resolve().parents[1]

def test_loads_seven_specs():
    corpus = load_specs(REPO / "config" / "specs.yaml")
    assert len(corpus.specs) == 7
    assert {s.spec_id for s in corpus.specs} == {
        "38.300", "38.331", "38.323", "38.322", "38.321", "28.545", "28.552",
    }

def test_series_is_derived_consistently():
    corpus = load_specs(REPO / "config" / "specs.yaml")
    for spec in corpus.specs:
        assert spec.spec_id.startswith(spec.series)

def test_versions_start_unset(tmp_path):
    # Exercise load_specs' handling of unset release/versions against a synthetic
    # fixture, so the test doesn't depend on the now-pinned live config.
    unset_yaml = tmp_path / "specs.yaml"
    unset_yaml.write_text(
        "release: null\n"
        "specs:\n"
        "  - spec_id: '38.331'\n"
        "    series: '38'\n"
        "    title: NR RRC\n"
        "    role: CU\n"
        "    version: null\n",
        encoding="utf-8",
    )
    corpus = load_specs(unset_yaml)
    assert all(s.version is None for s in corpus.specs)
    assert corpus.release is None

def test_settings_load_from_live_config():
    settings = load_settings(REPO / "config" / "settings.yaml")
    assert settings.top_k == 8
    assert settings.embedding_model == "BAAI/bge-small-en-v1.5"
    # Once fitted by calibration, the thresholds must be real floats, not unset.
    assert isinstance(settings.cosine_threshold, float)
    assert isinstance(settings.bm25_threshold, float)

def test_settings_handle_unset_thresholds(tmp_path):
    # Exercise load_settings' handling of unset thresholds against a synthetic
    # fixture, so the test doesn't depend on the now-fitted live config.
    unset_yaml = tmp_path / "settings.yaml"
    unset_yaml.write_text(
        "embedding_model: 'BAAI/bge-small-en-v1.5'\n"
        "top_k: 8\n"
        "max_chunk_chars: 6000\n"
        "session_cap: 20\n"
        "daily_cap: 500\n"
        "cosine_threshold: null\n"
        "bm25_threshold: null\n",
        encoding="utf-8",
    )
    settings = load_settings(unset_yaml)
    assert settings.cosine_threshold is None
    assert settings.bm25_threshold is None

def test_missing_file_raises_clear_error():
    with pytest.raises(FileNotFoundError, match="nope.yaml"):
        load_specs(Path("nope.yaml"))
