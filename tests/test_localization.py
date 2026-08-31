from ra2_explorer.localization import (
    localize_game_text,
    localized_fuzzy_search_match,
    localized_mixed_search_match,
    localized_search_match,
    pinyin_search_aliases,
    pinyin_search_match,
)


def test_game_text_defaults_can_be_simplified_without_losing_traditional_search() -> None:
    assert localize_game_text("戰鬥要塞", "zh-CN") == "战斗要塞"
    assert localize_game_text("戰鬥要塞", "zh-TW") == "戰鬥要塞"
    assert localized_search_match("战斗要塞", "戰鬥要塞 BFRT")
    assert localized_search_match("戰鬥要塞", "战斗要塞 BFRT")


def test_unit_name_fuzzy_search_accepts_a_tightly_bounded_subsequence() -> None:
    assert localized_fuzzy_search_match("航母", "航空母舰")
    assert localized_fuzzy_search_match("航母", "航空母艦")
    assert localized_fuzzy_search_match("航母", "航程很远的母舰与航空母舰")
    assert not localized_fuzzy_search_match("航母", "航空发动机")


def test_unit_names_expose_full_pinyin_and_initial_search_aliases() -> None:
    assert pinyin_search_aliases("超时空军团兵") == {
        "pinyin": "chao shi kong jun tuan bing",
        "pinyin_compact": "chaoshikongjuntuanbing",
        "pinyin_initials": "cskjtb",
    }
    assert pinyin_search_match("chaoshikong", "超时空军团兵")
    assert pinyin_search_match("cskjtb", "超时空军团兵")
    assert pinyin_search_match("hangmu", "航空母舰")
    assert not pinyin_search_match("hm", "航空发动机")


def test_mixed_search_matches_each_script_segment_across_names_and_aliases() -> None:
    assert localized_mixed_search_match("尤里 yuri", "尤里X", "Yuri Prime")
    assert localized_mixed_search_match("航mu", "航空母舰")
    assert localized_mixed_search_match("测试 bing", "測試步兵")
    assert not localized_mixed_search_match("盟军 yuri", "尤里X", "Yuri Prime")
