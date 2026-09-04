"""
Extracts seniority signals from unstructured job description text:
explicit level keywords (e.g. "entry level", "senior") and stated
years-of-experience requirements (e.g. "2+ years", "0-2 years").
"""
import re
import pandas as pd

# --- Years of experience patterns -------------------------------------

# Matches things like: "2+ years", "3-5 years of experience", "at least 4 years"
YEARS_RANGE_RE = re.compile(
    r"(\d{1,2})\s*(?:-|to|–|—)\s*(\d{1,2})\s*\+?\s*years?",
    re.IGNORECASE,
)

YEARS_PLUS_RE = re.compile(
    r"(\d{1,2})\s*\+\s*years?",
    re.IGNORECASE,
)

YEARS_MIN_RE = re.compile(
    r"(?:minimum|min\.?|at least)\s*(?:of\s*)?(\d{1,2})\s*years?",
    re.IGNORECASE,
)

YEARS_SIMPLE_RE = re.compile(
    r"(\d{1,2})\s*years?\s*(?:of\s*)?(?:relevant\s*)?experience",
    re.IGNORECASE,
)


def get_years_experience(description):
    """
    Return (min_years, max_years) required, inferred from description text.
    Falls back to (pd.NA, pd.NA) if nothing is found.
    """
    if not description:
        return pd.NA, pd.NA

    range_match = YEARS_RANGE_RE.search(description)
    if range_match:
        lo, hi = sorted([int(range_match.group(1)), int(range_match.group(2))])
        return lo, hi

    plus_match = YEARS_PLUS_RE.search(description)
    if plus_match:
        lo = int(plus_match.group(1))
        return lo, pd.NA

    min_match = YEARS_MIN_RE.search(description)
    if min_match:
        lo = int(min_match.group(1))
        return lo, pd.NA

    simple_match = YEARS_SIMPLE_RE.search(description)
    if simple_match:
        lo = int(simple_match.group(1))
        return lo, lo

    return pd.NA, pd.NA


def get_seniority_level(description, min_years=None):
    """
    Classify a posting as 'Entry-level', 'Mid-level', or 'Senior' based
    purely on stated years-of-experience. Returns pd.NA when no years
    figure could be extracted from the description.
    """
    if min_years is None or pd.isna(min_years):
        return pd.NA

    if min_years <= 2:
        return "Entry-level"
    elif min_years <= 5:
        return "Mid-level"
    elif min_years > 5:
        return "Senior"
    else:
        return pd.NA