from ra2_explorer.localization import localize_game_text, localized_search_match


def test_game_text_defaults_can_be_simplified_without_losing_traditional_search() -> None:
    assert localize_game_text("戰鬥要塞", "zh-CN") == "战斗要塞"
    assert localize_game_text("戰鬥要塞", "zh-TW") == "戰鬥要塞"
    assert localized_search_match("战斗要塞", "戰鬥要塞 BFRT")
    assert localized_search_match("戰鬥要塞", "战斗要塞 BFRT")
