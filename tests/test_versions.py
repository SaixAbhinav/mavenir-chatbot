import pytest
from noc_copilot.versions import encode_version, decode_version, release_of

@pytest.mark.parametrize("version,code", [
    ("17.5.0", "h50"),
    ("16.9.0", "g90"),
    ("15.5.0", "f50"),
    ("15.2.0", "f20"),
    ("18.1.0", "i10"),
    ("9.9.9", "999"),
    ("35.0.0", "z00"),
])
def test_roundtrip(version, code):
    assert encode_version(version) == code
    assert decode_version(code) == version

def test_release_of():
    assert release_of("17.5.0") == 17
    assert release_of("18.1.0") == 18

def test_rejects_out_of_range_part():
    with pytest.raises(ValueError, match="cannot be encoded"):
        encode_version("36.0.0")

def test_rejects_malformed_version():
    with pytest.raises(ValueError, match="three parts"):
        encode_version("17.5")

def test_rejects_malformed_code():
    with pytest.raises(ValueError, match="three characters"):
        decode_version("h5")
