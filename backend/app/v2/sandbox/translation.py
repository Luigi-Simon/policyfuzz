"""English projection tools. No IDs or structural metadata enter translation."""

import re
import unicodedata
from collections import Counter

from pydantic import BaseModel, ConfigDict


class EnglishText(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    text: str
    language: str
    translated: bool


def latin_display(text: str) -> bool:
    """Script check only; actual language classification belongs to the provider."""
    return bool(text.strip()) and all(
        not char.isalpha() or "LATIN" in unicodedata.name(char, "") for char in text
    )


def checked_projection(original: str, projection: EnglishText) -> EnglishText:
    if not latin_display(projection.text):
        raise ValueError("Non-English script or empty translation")
    if not projection.translated:
        if projection.language.casefold() != "english" or projection.text != original:
            raise ValueError("Invalid original-English claim")
    elif projection.text == original or not projection.language.strip():
        raise ValueError("Translation unchanged or source language missing")
    # Conservative: numerals, signs, limits and amounts must survive translation.
    number = r"[-+]?\d+(?:[.,]\d+)*%?"
    if Counter(re.findall(number, original)) != Counter(
        re.findall(number, projection.text)
    ):
        raise ValueError("Translation changed a numeral or amount")
    return projection
