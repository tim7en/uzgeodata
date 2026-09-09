"""Fix mixed-alphabet Cyrillic and produce a stable Latin form for it.

The hydromet deliveries were typed with a keyboard-layout toggle that sometimes
lagged: a word meant entirely in Cyrillic starts, or contains, a Latin letter
that happens to be drawn identically in both alphabets ("Cырдарья" is Latin C
followed by five Cyrillic letters, not a foreign word). left uncorrected, this
silently splits one station or river into two spellings that never match each
other. normalize_cyrillic() repairs that by alphabet, not by a name list: a
letter is only rewritten when the rest of its word is unambiguously Cyrillic.

transliterate() then produces the Latin form this project already uses in the
air-temperature workbooks (Ойгаинг -> Oygaing, Сурхандарья -> Surkhandarya):
practical English-exonym transliteration, not the ISO 9 or Uzbek Latin
alphabets, because that is the spelling the delivered data already committed
to and the two must not disagree for the same station.
"""

from __future__ import annotations

import re
import math
import unicodedata

# Uppercase and lowercase Latin letters that are drawn identically to a Cyrillic
# letter. Only these are ever candidates for repair.
_HOMOGLYPH_LATIN_TO_CYRILLIC = {
    "A": "А", "B": "В", "E": "Е", "K": "К", "M": "М", "H": "Н",
    "O": "О", "P": "Р", "C": "С", "T": "Т", "X": "Х", "Y": "У",
    "a": "а", "e": "е", "o": "о", "p": "р", "c": "с", "x": "х", "y": "у",
}
# Cyrillic letters with no Latin lookalike. A word containing one of these is
# unambiguously Cyrillic, which is what licenses fixing its homoglyph letters.
_CYRILLIC_ONLY = set("бгджзийклнптфцчшщъыьэюяБГДЖЗИЙЛНПФЦЧШЩЪЫЬЭЮЯ")

_WORD = re.compile(r"[A-Za-zА-ЯЁа-яё]+")


def normalize_cyrillic(text: str) -> str:
    """Rewrite homoglyph Latin letters back to Cyrillic, word by word."""
    if not text:
        return text

    def fix(match: re.Match) -> str:
        word = match.group(0)
        if not any(letter in _CYRILLIC_ONLY for letter in word):
            return word  # a genuine Latin word (a WMO name, a unit) - leave it
        return "".join(_HOMOGLYPH_LATIN_TO_CYRILLIC.get(ch, ch) for ch in word)

    return _WORD.sub(fix, text)


# Practical transliteration, matched to the spellings already committed to in
# this project's air-temperature workbooks (е.g. "Джизак" as Jizzak needs no
# override here, only case): digraphs first, then single letters.
_DIGRAPHS = [
    ("дж", "j"), ("Дж", "J"), ("ДЖ", "J"),
    ("щ", "shch"), ("Щ", "Shch"),
    ("ю", "yu"), ("Ю", "Yu"),
    ("я", "ya"), ("Я", "Ya"),
    ("х", "kh"), ("Х", "Kh"),
    ("ц", "ts"), ("Ц", "Ts"),
    ("ч", "ch"), ("Ч", "Ch"),
    ("ш", "sh"), ("Ш", "Sh"),
    ("ё", "yo"), ("Ё", "Yo"),
    ("ж", "j"), ("Ж", "J"),
]
_SINGLE = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "ы": "y",
    "э": "e", "ъ": "", "ь": "",
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "З": "Z",
    "И": "I", "Й": "Y", "К": "K", "Л": "L", "М": "M", "Н": "N", "О": "O",
    "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U", "Ф": "F", "Ы": "Y",
    "Э": "E", "Ъ": "", "Ь": "",
}


def transliterate(text: str) -> str:
    """Cyrillic -> Latin. Text already in Latin (or mixed) passes through."""
    if not text:
        return text
    result = normalize_cyrillic(text)
    for cyrillic, latin in _DIGRAPHS:
        result = result.replace(cyrillic, latin)
    result = "".join(_SINGLE.get(ch, ch) for ch in result)
    return result


def has_cyrillic(text: str) -> bool:
    return bool(text) and any("а" <= ch.lower() <= "я" or ch.lower() == "ё" for ch in text)


def clean_text(value) -> str:
    """Trimmed, whitespace-collapsed string, or "" for a blank cell."""
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return ""
    text = unicodedata.normalize("NFC", str(value))
    return re.sub(r"\s+", " ", text).strip()
