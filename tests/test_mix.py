from __future__ import annotations

import hashlib
import struct

import pytest

from ra2_explorer.codecs.mix import (
    MixHashType,
    _derive_blowfish_key,
    build_mix,
    parse_mix,
    ra2_mix_hash,
    resolve_mix_names,
)
from ra2_explorer.errors import InvalidFormatError


def test_encrypted_ra2_mix_round_trip() -> None:
    key_source_hash = hashlib.sha256(b"cnc-formats-test-keysource").digest()
    key_source = key_source_hash + key_source_hash + key_source_hash[:16]
    archive = build_mix(
        [("demo.shp", b"sprite"), ("rules.ini", b"[General]\n")],
        hash_type=MixHashType.RA2,
        encrypted=True,
        key_source=key_source,
    )

    index = parse_mix(archive)
    names = ("demo.shp", "rules.ini")
    hash_type, resolved = resolve_mix_names(index.entries, names)

    assert index.encrypted is True
    assert hash_type is MixHashType.RA2
    assert set(resolved.values()) == set(names)
    sprite_entry = next(entry for entry in index.entries if entry.crc == ra2_mix_hash("demo.shp"))
    assert bytes(index.payload(archive, sprite_entry)) == b"sprite"


def test_westwood_key_derivation_vector() -> None:
    key_source_hash = hashlib.sha256(b"cnc-formats-test-keysource").digest()
    key_source = key_source_hash + key_source_hash + key_source_hash[:16]

    assert _derive_blowfish_key(key_source).hex() == (
        "7f578c161987d9df1d22ee15d72f9fe35680bab2ce2e7c7b"
        "a068fbb4dd9a5c1c396a3e0f2a526fb73770c90ce81bf2ff"
        "e72cac5b87fa7444"
    )


def test_mix_rejects_entry_outside_declared_data() -> None:
    malformed = bytearray(struct.pack("<HI", 1, 2))
    malformed.extend(struct.pack("<III", 1, 1, 5))
    malformed.extend(b"xx")

    with pytest.raises(InvalidFormatError, match="declared data section"):
        parse_mix(malformed)
