"""Find numbers in prose and compare them under the rounding the text states."""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# Digits that are not measurements: dates, IDs (P1-Q2, EV-1.1, FE-01), and words mixing
# letters and digits (S13, Q4, 3a, 31st, SYN_MID_ATLANTIC_MEDICARE_PART_D_1).
_NOT_NUMBERS = [
    re.compile(r"§\s*\d+(?:\.\d+)?"),  # a memo section reference (§3.1) is an identifier (brief-003, brief-006)
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b[A-Za-z]{1,4}\d*-[A-Za-z]?\d+(?:\.\d+)?\b"),
    re.compile(r"\b\w*[A-Za-z_]\w*\d\w*\b|\b\d+[A-Za-z_]\w*\b"),
]
_NUMBER = re.compile(r"(?<![\w.,])([-−–]?)(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?!\w)(%?)")
_TOKEN = re.compile(r"[-−–]?\d[\d,]*(?:\.\d+)?%?|[a-z]+(?:[-'][a-z]+)*")


@dataclass(frozen=True)
class Number:
    value: float
    decimals: int
    percent: bool
    text: str


def _parse(sign: str, whole: str, frac: str | None, pct: str, text: str) -> Number:
    value = float(whole.replace(",", "") + (frac or ""))
    return Number(-value if sign else value, len(frac) - 1 if frac else 0, bool(pct), text)


def parse_token(token: str) -> Number | None:
    m = _NUMBER.fullmatch(token.strip())
    return _parse(*m.groups(), token) if m else None


def extract(text: str) -> list[Number]:
    """Numbers worth checking: years and small counts (0 to 10) are left out."""
    for pattern in _NOT_NUMBERS:
        text = pattern.sub(" ", text)
    found = []
    for m in _NUMBER.finditer(text):
        n = _parse(*m.groups(), m.group(0))
        is_year = n.decimals == 0 and not n.percent and "," not in m.group(2) and 1990 <= n.value <= 2099
        small = n.decimals == 0 and not n.percent and abs(n.value) <= 10
        if not (is_year or small):
            found.append(n)
    return found


def _rounded(x: float, decimals: int) -> Decimal:
    return Decimal(str(x)).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)


def same(a: Number, b: Number) -> bool:
    """Equal once the more precise value is rounded to the other's stated precision; sign ignored."""
    x, y = abs(a.value), abs(b.value)
    return _rounded(y, a.decimals) == _rounded(x, a.decimals) or _rounded(x, b.decimals) == _rounded(y, b.decimals)


def as_numbers(values) -> list[Number]:
    out = []
    for v in values:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            text = repr(v)
            out.append(Number(float(v), len(text.split(".")[1]) if "." in text else 0, False, text))
    return out


def tokens(text: str) -> list[str]:
    text = text.lower().replace("’", "'").replace("“", '"').replace("”", '"')
    return _TOKEN.findall(text)


def _token_equal(phrase_token: str, text_token: str) -> bool:
    if phrase_token == "x":  # "saves X hours": X stands for any value
        return True
    a, b = parse_token(phrase_token), parse_token(text_token)
    if a or b:
        return bool(a and b and same(a, b))
    return phrase_token == text_token


def contains_phrase(text: str, phrase: str, slack: int = 2) -> bool:
    """True when the phrase's words appear in order, with at most `slack` extra words between them."""
    want, have = tokens(phrase), tokens(text)
    if not want:
        return False
    for start, token in enumerate(have):
        if not _token_equal(want[0], token):
            continue
        limit, pos, ok = start + len(want) + slack, start, True
        for w in want[1:]:
            pos += 1
            while pos < min(limit, len(have)) and not _token_equal(w, have[pos]):
                pos += 1
            if pos >= min(limit, len(have)):
                ok = False
                break
        if ok:
            return True
    return False
