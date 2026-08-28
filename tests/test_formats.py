from __future__ import annotations

from ra2_explorer.codecs.csf import parse_csf
from ra2_explorer.codecs.hva import parse_hva
from ra2_explorer.codecs.sniff import sniff_format
from ra2_explorer.codecs.tmp import parse_tmp
from ra2_explorer.codecs.vxl import parse_vxl
from ra2_explorer.demo import (
    _build_demo_csf,
    _build_demo_hva,
    _build_demo_palette,
    _build_demo_tmp,
    _build_demo_vxl,
)


def test_csf_decodes_inverted_utf16_and_extra_value() -> None:
    data = _build_demo_csf()
    strings = parse_csf(data)

    assert sniff_format(data) == "csf"
    assert strings.string_count == 3
    assert strings.labels[1].values[0].text == "Asset pipeline ready."
    assert strings.labels[1].values[0].extra == "explorer-ready"


def test_vxl_decodes_columns_and_renders_embedded_palette() -> None:
    data = _build_demo_vxl(_build_demo_palette())
    model = parse_vxl(data)

    assert sniff_format(data) == "vxl"
    assert len(model.limbs) == 1
    assert model.limbs[0].name == "BODY"
    assert model.limbs[0].size == (12, 8, 7)
    assert model.voxel_count > 80
    preview = model.render(scale=2)
    assert preview.mode == "RGBA"
    assert preview.getbbox() is not None


def test_hva_reads_frame_section_matrices() -> None:
    data = _build_demo_hva()
    animation = parse_hva(data)

    assert sniff_format(data) == "hva"
    assert animation.frame_count == 4
    assert animation.section_names == ("BODY",)
    assert animation.transform(3, 0)[3] > animation.transform(0, 0)[3]


def test_tmp_reads_real_ts_ra2_layout_and_renders_diamond() -> None:
    data = _build_demo_tmp()
    template = parse_tmp(data)

    assert sniff_format(data) == "tmp"
    assert template.tile_width == 60
    assert template.tile_height == 30
    assert template.tile_count == 1
    preview = template.render(scale=1)
    assert preview.size == (60, 30)
    assert preview.getbbox() is not None
