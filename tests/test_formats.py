from __future__ import annotations

import struct

from ra2_explorer.codecs.aud import aud_for_browser, parse_aud
from ra2_explorer.codecs.bag import (
    bag_audio_for_browser,
    parse_bag_index,
)
from ra2_explorer.codecs.csf import parse_csf
from ra2_explorer.codecs.hva import parse_hva
from ra2_explorer.codecs.pal import parse_palette
from ra2_explorer.codecs.sniff import sniff_format
from ra2_explorer.codecs.text import parse_ini
from ra2_explorer.codecs.tmp import parse_tmp
from ra2_explorer.codecs.vxl import (
    VxlRenderPart,
    build_vxl_scene,
    parse_vxl,
    render_vxl_composite,
)
from ra2_explorer.codecs.wav import parse_wav, wav_for_browser
from tests.ra2_fixtures import (
    _build_fixture_csf,
    _build_fixture_hva,
    _build_fixture_palette,
    _build_fixture_shp,
    _build_fixture_tmp,
    _build_fixture_vxl,
    _build_fixture_wav,
)


def test_csf_decodes_inverted_utf16_and_extra_value() -> None:
    data = _build_fixture_csf()
    strings = parse_csf(data)

    assert sniff_format(data) == "csf"
    assert strings.string_count == 5
    assert strings.labels[1].values[0].text == "Asset pipeline ready."
    assert strings.labels[1].values[0].extra == "explorer-ready"


def test_vxl_decodes_columns_and_renders_embedded_palette() -> None:
    data = _build_fixture_vxl(_build_fixture_palette())
    model = parse_vxl(data)

    assert sniff_format(data) == "vxl"
    assert len(model.limbs) == 1
    assert model.limbs[0].name == "BODY"
    assert model.limbs[0].size == (12, 8, 7)
    assert model.voxel_count > 80
    preview = model.render(scale=2)
    assert preview.mode == "RGBA"
    assert preview.getbbox() is not None


def test_palette_player_remap_preserves_unrelated_colors() -> None:
    palette = parse_palette(_build_fixture_palette())

    remapped = palette.with_player_color("blue")

    assert remapped.colors[:16] == palette.colors[:16]
    assert remapped.colors[32:] == palette.colors[32:]
    assert remapped.colors[16:32] != palette.colors[16:32]
    assert remapped.colors[31][2] > remapped.colors[31][0]


def test_hva_reads_frame_section_matrices() -> None:
    data = _build_fixture_hva()
    animation = parse_hva(data)

    assert sniff_format(data) == "hva"
    assert animation.frame_count == 4
    assert animation.section_names == ("BODY",)
    assert animation.transform(3, 0)[3] > animation.transform(0, 0)[3]


def test_vxl_composite_applies_hva_facing_and_player_color() -> None:
    model = parse_vxl(_build_fixture_vxl(_build_fixture_palette()))
    animation = parse_hva(_build_fixture_hva())
    part = VxlRenderPart(model, animation)

    front = render_vxl_composite([part], frame=0, facing=0, scale=2)
    moved = render_vxl_composite([part], frame=3, facing=2, scale=2)
    blue = render_vxl_composite(
        [part],
        frame=0,
        facing=0,
        player_color="blue",
        scale=2,
    )

    assert front.getbbox() is not None
    assert moved.getbbox() is not None
    assert front.size != moved.size or front.tobytes() != moved.tobytes()
    assert front.tobytes() != blue.tobytes()

    scene = build_vxl_scene([part], frame=3, player_color="blue").as_dict()
    assert scene["frame"] == 3
    assert scene["frame_count"] == 4
    assert scene["voxel_count"] == model.voxel_count
    assert scene["visible_voxel_count"] == len(scene["voxels"])
    assert scene["visible_voxel_count"] < model.voxel_count
    assert scene["bounds"]["max"][2] > scene["bounds"]["min"][2]


def test_ini_accepts_retail_section_headers_with_inline_comments() -> None:
    parsed = parse_ini(b"[MTNK] ; Apocalypse tank\r\nVoxel=yes\r\n")

    assert parsed.sections[0].name == "MTNK"
    assert parsed.sections[0].entries[0].key == "Voxel"
    assert parsed.sections[0].entries[0].value == "yes"


def test_tmp_reads_real_ts_ra2_layout_and_renders_diamond() -> None:
    data = _build_fixture_tmp()
    template = parse_tmp(data)

    assert sniff_format(data) == "tmp"
    assert template.tile_width == 60
    assert template.tile_height == 30
    assert template.tile_count == 1
    preview = template.render(scale=1)
    assert preview.size == (60, 30)
    assert preview.getbbox() is not None
    assert sniff_format(b"", "NEWTILE.UBN") == "tmp"
    assert sniff_format(b"", "MOONTILE.LUN") == "tmp"
    assert sniff_format(_build_fixture_shp(), "GEM07.DES") == "shp"


def test_wav_reads_riff_metadata_without_requiring_pcm_codec() -> None:
    audio = parse_wav(_build_fixture_wav())

    assert audio.audio_format == 1
    assert audio.channels == 1
    assert audio.sample_rate == 11_025
    assert 0.3 < audio.duration_seconds < 0.4


def test_ima_adpcm_wav_is_transcoded_to_browser_pcm() -> None:
    block_align = 8
    samples_per_block = 9
    fmt = struct.pack(
        "<HHIIHHHH",
        0x11,
        1,
        8_000,
        8_000 * block_align // samples_per_block,
        block_align,
        4,
        2,
        samples_per_block,
    )
    block = struct.pack("<hBB", 0, 0, 0) + bytes((0x11, 0x22, 0x34, 0x87))
    body = (
        b"WAVEfmt "
        + struct.pack("<I", len(fmt))
        + fmt
        + b"fact"
        + struct.pack("<II", 4, samples_per_block)
        + b"data"
        + struct.pack("<I", len(block))
        + block
    )
    encoded = b"RIFF" + struct.pack("<I", len(body)) + body

    pcm, transcoded = wav_for_browser(encoded)

    assert transcoded is True
    assert parse_wav(pcm).audio_format == 1
    assert parse_wav(pcm).data_size == samples_per_block * 2


def test_audio_idx_expands_pcm_and_ima_bag_entries() -> None:
    pcm_entry = struct.pack(
        "<16sIIIII",
        b"unitpcm\0",
        0,
        8,
        22_050,
        0x06,
        0,
    )
    ima_entry = struct.pack(
        "<16sIIIII",
        b"unitima\0",
        8,
        8,
        8_000,
        0x0C,
        8,
    )
    index = parse_bag_index(
        b"GABA" + struct.pack("<II", 2, 2) + pcm_entry + ima_entry,
        bag_size=16,
    )

    assert [entry.name for entry in index.entries] == ["unitpcm", "unitima"]
    assert index.entries[0].codec == "pcm16"
    assert index.entries[1].codec == "ima_adpcm"
    ima_block = struct.pack("<hBB", 0, 0, 0) + bytes((0x11, 0x22, 0x34, 0x87))
    playable = bag_audio_for_browser(ima_block, index.entries[1])
    assert parse_wav(playable).audio_format == 1
    assert parse_wav(playable).data_size == 18


def test_aud_decodes_ima_and_westwood_chunks_to_pcm_wav() -> None:
    ima_payload = bytes((0x11, 0x22, 0x34, 0x87))
    ima_chunk = struct.pack("<HHI", len(ima_payload), 16, 0xDEAF) + ima_payload
    ima_aud = struct.pack("<HIIBB", 8_000, len(ima_chunk), 16, 0x02, 99) + ima_chunk

    ima_metadata = parse_aud(ima_aud)
    ima_wav = aud_for_browser(ima_aud)

    assert ima_metadata.codec == "ima_adpcm"
    assert ima_metadata.sample_count == 8
    assert parse_wav(ima_wav).data_size == 16

    westwood_payload = bytes((0x82, 120, 128, 136))
    westwood_chunk = (
        struct.pack("<HHI", len(westwood_payload), 3, 0xDEAF) + westwood_payload
    )
    westwood_aud = (
        struct.pack("<HIIBB", 11_025, len(westwood_chunk), 3, 0, 1)
        + westwood_chunk
    )

    westwood_wav = aud_for_browser(westwood_aud)
    assert parse_wav(westwood_wav).bits_per_sample == 8
    assert parse_wav(westwood_wav).data_size == 3
