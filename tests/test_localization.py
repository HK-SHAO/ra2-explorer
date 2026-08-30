from ra2_explorer.localization import (
    localize_game_text,
    localized_fuzzy_search_match,
    localized_search_match,
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
