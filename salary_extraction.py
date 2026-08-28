"""
Extracts salary ranges from unstructured job description text.

Handles: hourly vs. annual pay, ranges vs. single values, and common
false positives (401k, percentages, headcount figures).
"""
import re
import pandas as pd

KEYWORDS = [
    "salary", "salaries", "compensation", "comp", "pay", "wage", "wages",
    "hourly rate", "remuneration", "usd",
]

WINDOW_WORDS = 20

HOURLY_HINTS = re.compile(
    r"(/\s*hr\b|/\s*hour\b|per\s*hour\b|hourly\b|an\s*hour\b|/\s*hrs\b)",
    re.IGNORECASE,
)

CURRENCY_PREFIX = r"(?:USD|CAD|GBP|EUR|AUD)?\s*\$?"

NUM_DIGITS = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
NUM = rf"{CURRENCY_PREFIX}\s*({NUM_DIGITS})\s*(k|K)?"

RANGE_RE = re.compile(
    rf"{NUM}\s*(?:-|–|—|to|through)\s*{NUM}",
    re.IGNORECASE,
)

SINGLE_RE = re.compile(NUM)

PERCENT_AFTER = re.compile(r"\s*(%|percent\b)", re.IGNORECASE)

NONSALARY_AFTER = re.compile(
    r"\s*(month|months|year|years|week|weeks|day|days|"
    r"employee|employees|people|person|hire|hires)\b",
    re.IGNORECASE,
)

HOURS_PER_YEAR = 40 * 52

MIN_PLAUSIBLE = 5

BARE_MONEY_RANGE_RE = re.compile(
    r"(\d{1,3}(?:,\d{3})*\.\d{2})\s*(?:-|–|—|to|through)\s*(\d{1,3}(?:,\d{3})*\.\d{2})",
    re.IGNORECASE,
)

BARE_MONEY_MIN = 1000
BARE_MONEY_MAX = 1_000_000

RETIREMENT_PLAN_RE = re.compile(
    r"\b40[13]\s*\(?\s*k\s*\)?\b|\b40[13]\s*\(?\s*b\s*\)?\b|\b457\s*\(?\s*b\s*\)?\b",
    re.IGNORECASE,
)


def _to_number(raw: str, k_suffix: str) -> float:
    value = float(raw.replace(",", ""))
    if k_suffix:
        value *= 1000
    return value


def _annualize(value: float, is_hourly: bool) -> float:
    return value * HOURS_PER_YEAR if is_hourly else value


def _is_disqualified(window_text: str, match) -> bool:
    tail = window_text[match.end():match.end() + 14]
    return bool(PERCENT_AFTER.match(tail)) or bool(NONSALARY_AFTER.match(tail))


def _candidates_for_window(window_text):
    is_hourly = bool(HOURLY_HINTS.search(window_text))
    out = []

    for range_match in RANGE_RE.finditer(window_text):
        if _is_disqualified(window_text, range_match):
            continue
        num1, k1, num2, k2 = range_match.groups()
        # Share a "k" suffix across both numbers if only one side has it,
        # e.g. "$125-$165k" means 125k-165k, not 125-165000.
        if k2 and not k1:
            k1 = k2
        elif k1 and not k2:
            k2 = k1
        raw1 = _to_number(num1, k1)
        raw2 = _to_number(num2, k2)
        if raw1 < MIN_PLAUSIBLE or raw2 < MIN_PLAUSIBLE:
            continue
        v1 = _annualize(raw1, is_hourly)
        v2 = _annualize(raw2, is_hourly)
        lo, hi = sorted([v1, v2])
        has_dollar = bool(re.search(r"\$|USD|CAD|GBP|EUR|AUD", range_match.group(0)))
        out.append((3 if has_dollar else 1, lo, hi))

    for single_match in SINGLE_RE.finditer(window_text):
        if _is_disqualified(window_text, single_match):
            continue
        num, k = single_match.groups()
        raw = _to_number(num, k)
        if raw < MIN_PLAUSIBLE:
            continue
        v = _annualize(raw, is_hourly)
        has_dollar = bool(re.search(r"\$|USD|CAD|GBP|EUR|AUD", single_match.group(0)))
        out.append((2 if has_dollar else 0, v, v))

    return out


def get_salary(description):
    """Extract a (min, max) annual salary estimate from raw job description text."""
    if not description:
        return pd.NA, pd.NA

    text = RETIREMENT_PLAN_RE.sub(" ", description)
    words = text.split()

    keyword_pattern = re.compile(
        r"\b(" + "|".join(re.escape(k) for k in KEYWORDS) + r")\b",
        re.IGNORECASE,
    )

    all_candidates = []

    for match in keyword_pattern.finditer(text):
        start_char = match.start()
        prefix_word_count = len(text[:start_char].split())

        win_start_word = max(0, prefix_word_count - WINDOW_WORDS)
        win_end_word = min(len(words), prefix_word_count + WINDOW_WORDS + 1)
        window_text = " ".join(words[win_start_word:win_end_word])

        all_candidates.extend(_candidates_for_window(window_text))

    if not all_candidates:
        for m in BARE_MONEY_RANGE_RE.finditer(text):
            v1 = float(m.group(1).replace(",", ""))
            v2 = float(m.group(2).replace(",", ""))
            if BARE_MONEY_MIN <= v1 <= BARE_MONEY_MAX and BARE_MONEY_MIN <= v2 <= BARE_MONEY_MAX:
                lo, hi = sorted([v1, v2])
                return lo, hi
        return pd.NA, pd.NA

    best_tier = max(c[0] for c in all_candidates)
    for tier, lo, hi in all_candidates:
        if tier == best_tier:
            return lo, hi

    return pd.NA, pd.NA
