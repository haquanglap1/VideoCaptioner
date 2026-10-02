"""Conservative, opt-in Vietnamese spoken-word suggestions; never mutate subtitles."""

import re
from dataclasses import dataclass

_DIGITS = ("không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín")
_UNITS = {"kg": "ki lô gam", "g": "gam", "km": "ki lô mét", "cm": "xen ti mét",
    "mm": "mi li mét", "m": "mét", "ml": "mi li lít", "l": "lít", "%": "phần trăm",
    "°C": "độ xê", "VND": "đồng", "USD": "đô la Mỹ", "kWh": "ki lô oát giờ"}
_NUMBER = re.compile(r"(?<![\w.,:/+\-])([+-]?\d+(?:[.,:/\-]\d+)*)(?:\s*(" +
    "|".join(re.escape(unit) for unit in sorted(_UNITS, key=len, reverse=True)) + r")(?!\w))?(?!\w|[.,:/\-]\d)")
_ABBREVIATIONS = {"TP.HCM": "thành phố Hồ Chí Minh", "TP.": "thành phố", "UBND": "ủy ban nhân dân"}


@dataclass(frozen=True)
class SpokenTextSuggestion:
    text: str
    warnings: tuple[str, ...] = ()


def _hundreds(number: int, *, full: bool = False) -> str:
    hundreds, rest = divmod(number, 100)
    tens, ones = divmod(rest, 10)
    parts = [_DIGITS[hundreds], "trăm"] if hundreds or full else []
    if tens:
        parts.extend(["mười"] if tens == 1 else [_DIGITS[tens], "mươi"])
    elif ones and parts:
        parts.append("lẻ")
    if ones:
        parts.append("mốt" if ones == 1 and tens > 1 else "lăm" if ones == 5 and tens else _DIGITS[ones])
    return " ".join(parts)


def read_integer(number: int) -> str:
    if not 0 <= number < 1_000_000_000:
        raise ValueError("Vietnamese integer suggestion supports 0 through 999999999")
    if number == 0:
        return _DIGITS[0]
    parts = []
    for divisor, suffix in ((1_000_000, "triệu"), (1_000, "nghìn"), (1, "")):
        group, number = divmod(number, divisor)
        if group:
            parts.append(_hundreds(group, full=bool(parts) and group < 100))
            if suffix:
                parts.append(suffix)
    return " ".join(parts)


def suggest_vietnamese(text: str) -> SpokenTextSuggestion:
    """Expand only unambiguous numerals/units and an explicit abbreviation allowlist."""
    warnings = []
    def expand(match):
        raw, unit = match.groups()
        sign = "âm " if raw.startswith("-") else "dương " if raw.startswith("+") else ""
        value = raw.lstrip("+-")
        pieces = value.split(",")
        integer = pieces[0]
        if (len(pieces) > 2 or not all(piece.isdigit() for piece in pieces)
            or len(integer) > 9 or len(integer) > 1 and integer.startswith("0")):
            warnings.append("Giữ nguyên số, mã hoặc thời điểm mơ hồ: " + raw)
            return match.group()
        spoken = sign + read_integer(int(integer))
        if len(pieces) == 2:
            spoken += " phẩy " + " ".join(_DIGITS[int(char)] for char in pieces[1])
        return spoken + (" " + _UNITS[unit] if unit else "")

    result = _NUMBER.sub(expand, text)
    for abbreviation, spoken in _ABBREVIATIONS.items():
        result = re.sub(r"(?<!\w)" + re.escape(abbreviation) + r"(?!\w)", spoken, result)
    return SpokenTextSuggestion(result, tuple(dict.fromkeys(warnings)))
