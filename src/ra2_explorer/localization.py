from __future__ import annotations

import threading
from functools import lru_cache
from typing import Literal

from opencc import OpenCC

GameLanguage = Literal["zh-CN", "zh-TW"]
DEFAULT_GAME_LANGUAGE: GameLanguage = "zh-CN"

_converters = threading.local()


def localize_game_text(value: str | None, language: GameLanguage) -> str | None:
    if value is None or language == "zh-TW":
        return value
    return _convert(value, "t2s")


def localized_search_match(query: str, text: str) -> bool:
    haystack = text.casefold()
    return any(variant in haystack for variant in _query_variants(query))


def localized_fuzzy_search_match(query: str, text: str) -> bool:
    """Match a compact name query as an ordered, tightly bounded subsequence."""
    if localized_search_match(query, text):
        return True
    for variant in _query_variants(query):
        needle = _normalize_search_text(variant)
        if not _allows_fuzzy_match(needle):
            continue
        haystack = _normalize_search_text(text)
        if len(haystack) > max(64, len(needle) * 8):
            continue
        if _bounded_subsequence(needle, haystack):
            return True
    return False


def _normalize_search_text(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _allows_fuzzy_match(value: str) -> bool:
    has_cjk = any("\u3400" <= character <= "\u9fff" for character in value)
    return len(value) >= (2 if has_cjk else 4)


def _bounded_subsequence(needle: str, haystack: str) -> bool:
    first = haystack.find(needle[0])
    while first >= 0:
        cursor = first
        for character in needle[1:]:
            cursor = haystack.find(character, cursor + 1)
            if cursor < 0:
                break
        else:
            if cursor - first + 1 <= max(len(needle) * 2, len(needle) + 2):
                return True
        first = haystack.find(needle[0], first + 1)
    return False


@lru_cache(maxsize=2_048)
def _query_variants(query: str) -> tuple[str, ...]:
    values = (query, _convert(query, "t2s"), _convert(query, "s2t"))
    return tuple(dict.fromkeys(value.casefold() for value in values if value))


@lru_cache(maxsize=16_384)
def _convert(value: str, configuration: str) -> str:
    converter = getattr(_converters, configuration, None)
    if converter is None:
        converter = OpenCC(configuration)
        setattr(_converters, configuration, converter)
    return converter.convert(value)


__all__ = [
    "DEFAULT_GAME_LANGUAGE",
    "GameLanguage",
    "localized_fuzzy_search_match",
    "localized_search_match",
    "localize_game_text",
]
