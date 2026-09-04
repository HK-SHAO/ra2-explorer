from scripts.audit_media_translations import build_media_translation_audit


def test_build_media_translation_audit_reports_missing_original_translation() -> None:
    payload = build_media_translation_audit(
        [
            {
                "asset": {"id": "voice-1", "display_name": "Voice1.wav"},
                "kind": "voice",
                "groups": ["mission_voice"],
                "events": ["MissionOne"],
                "original_texts": ["Incoming transmission."],
                "localized_texts": ["收到传讯。"],
                "translated_texts": [],
            },
            {
                "asset": {"id": "sound-1", "display_name": "Sound1.wav"},
                "kind": "sound",
                "groups": ["interface_sound"],
                "events": ["MenuClick"],
                "original_texts": ["Click"],
                "localized_texts": [],
                "translated_texts": ["点击"],
            },
        ],
        "source",
    )

    assert payload["summary"]["media_asset_count"] == 2
    assert payload["summary"]["with_original_text"] == 2
    assert payload["summary"]["with_editorial_translation"] == 1
    assert payload["summary"]["missing_translation_for_original"] == 1
    assert payload["missing_translation_for_original"] == ["voice-1"]
    assert payload["summary"]["by_group"] == {
        "interface_sound": 1,
        "mission_voice": 1,
    }


def test_build_media_translation_audit_reuses_format_validation() -> None:
    payload = build_media_translation_audit(
        [
            {
                "asset": {"id": "voice-1", "display_name": "Voice1.wav"},
                "kind": "voice",
                "groups": [],
                "events": [],
                "original_texts": ["<Death sound>"],
                "localized_texts": [],
                "translated_texts": ["阵亡声"],
            }
        ],
        "source",
    )

    assert payload["summary"]["translation_format_violation_count"] == 1
    assert payload["translation_format_violations"][0]["reason"] == "missing-cue"
    assert payload["translation_format_violations"][0]["stem"] == "voice1"
