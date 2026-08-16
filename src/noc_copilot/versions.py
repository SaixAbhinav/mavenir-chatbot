"""3GPP filename version codes.

Each of the three version numbers is encoded as a single character:
0-9 for 0-9, then a-z for 10-35. v17.5.0 -> "h50".
"""
from __future__ import annotations

import string

_ALPHABET = string.digits + string.ascii_lowercase  # 36 symbols


def encode_version(version: str) -> str:
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"Version must have three parts, got {version!r}")
    out = []
    for part in parts:
        n = int(part)
        if not 0 <= n < len(_ALPHABET):
            raise ValueError(f"Version part {n} cannot be encoded (0-35 only)")
        out.append(_ALPHABET[n])
    return "".join(out)


def decode_version(code: str) -> str:
    if len(code) != 3:
        raise ValueError(f"Version code must be three characters, got {code!r}")
    return ".".join(str(_ALPHABET.index(c.lower())) for c in code)


def release_of(version: str) -> int:
    return int(version.split(".")[0])
