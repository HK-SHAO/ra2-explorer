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
    "localized_search_match",
    "localize_game_text",
]
