from __future__ import annotations

import json
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from ra2_explorer.reference_data import load_audio_transcript


def test_audio_transcript_reads_complete_list_and_normalizes_file_ids(tmp_path) -> None:
    path = tmp_path / "audio-transcript.xlsx"
    path.write_bytes(_audio_transcript_workbook())

    entries = load_audio_transcript(path)

    assert entries == {
        "giselea": {
            "text": "Sir, yes sir!",
            "unit": "GI",
            "category": "Select",
            "comments": "",
            "faction": "Allied",
        }
    }


def test_audio_transcript_ignores_invalid_workbook(tmp_path) -> None:
    path = tmp_path / "audio-transcript.xlsx"
    path.write_bytes(b"not an xlsx file")

    assert load_audio_transcript(path) == {}


def test_audio_transcript_merges_local_mission_supplement(tmp_path) -> None:
    workbook_path = tmp_path / "audio-transcript.xlsx"
    workbook_path.write_bytes(_audio_transcript_workbook())
    supplement_path = tmp_path / "mission-audio-transcript.json"
    supplement_path.write_text(
        json.dumps(
            {
                "entries": {
                    "$A01_P01.wav": {
                        "original_text": "Protect the Time Machine.",
                        "localized_text": "保护时间机器。",
                        "speaker": "EVA",
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    entries = load_audio_transcript(
        workbook_path, supplement_paths=(supplement_path,)
    )

    assert entries["giselea"]["text"] == "Sir, yes sir!"
    assert entries["a01_p01"] == {
        "original_text": "Protect the Time Machine.",
        "localized_text": "保护时间机器。",
        "speaker": "EVA",
        "text": "Protect the Time Machine.",
    }


def test_audio_transcript_can_load_supplement_without_workbook(tmp_path) -> None:
    supplement_path = tmp_path / "mission-audio-transcript.json"
    supplement_path.write_text(
        '{"entries":{"S02_P01":{"text":"Destroy Einstein lab."}}}',
        encoding="utf-8",
    )

    entries = load_audio_transcript(
        tmp_path / "missing.xlsx", supplement_paths=(supplement_path,)
    )

    assert entries["s02_p01"]["original_text"] == "Destroy Einstein lab."


def _audio_transcript_workbook() -> bytes:
    shared = ("File", "Line", "Unit", "Category", "Comments", "Faction")
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as workbook:
        workbook.writestr(
            "xl/sharedStrings.xml",
            "<?xml version='1.0' encoding='UTF-8'?>"
            "<sst xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'>"
            + "".join(f"<si><t>{value}</t></si>" for value in shared)
            + "</sst>",
        )
        workbook.writestr(
            "xl/workbook.xml",
            "<?xml version='1.0' encoding='UTF-8'?>"
            "<workbook xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main' "
            "xmlns:r='http://schemas.openxmlformats.org/officeDocument/2006/relationships'>"
            "<sheets><sheet name='Complete List' sheetId='1' r:id='rId1'/></sheets>"
            "</workbook>",
        )
        workbook.writestr(
            "xl/_rels/workbook.xml.rels",
            "<?xml version='1.0' encoding='UTF-8'?>"
            "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
            "<Relationship Id='rId1' Type='worksheet' Target='worksheets/sheet1.xml'/>"
            "</Relationships>",
        )
        workbook.writestr(
            "xl/worksheets/sheet1.xml",
            "<?xml version='1.0' encoding='UTF-8'?>"
            "<worksheet xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'>"
            "<sheetData>"
            "<row r='1'>"
            + "".join(
                f"<c r='{column}1' t='s'><v>{index}</v></c>"
                for index, column in enumerate("ABCDEF")
            )
            + "</row>"
            "<row r='2'>"
            "<c r='A2' t='inlineStr'><is><t>$giselea.wav</t></is></c>"
            "<c r='B2' t='inlineStr'><is><t>Sir, yes sir!</t></is></c>"
            "<c r='C2' t='inlineStr'><is><t>GI</t></is></c>"
            "<c r='D2' t='inlineStr'><is><t>Select</t></is></c>"
            "<c r='F2' t='inlineStr'><is><t>Allied</t></is></c>"
            "</row>"
            "</sheetData></worksheet>",
        )
    return output.getvalue()
