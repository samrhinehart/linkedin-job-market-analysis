"""
Cleans and parses raw text pulled from job cards and job detail panels:
locations, job titles, skill mentions, and posting dates.
"""
import logging
import re
from datetime import datetime, timedelta
import pandas as pd
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By

from salary_extraction import get_salary  # noqa: F401  (re-exported for convenience)

# Uses the same "scrape_log.txt" logger config set up in navigation.py
# (logging.basicConfig only takes effect once, on first call, so this
# picks up that same file/handler rather than creating a second one).
logger = logging.getLogger(__name__)


def split_loc(txt):
    """Split a raw location string like 'San Jose, CA (Hybrid)' into city, state, work_type."""
    if '(' in txt and ')' in txt:
        location = txt[:txt.rfind('(')].strip()
        work_type = txt[txt.rfind('(')+1:txt.rfind(')')].strip()
        if ', ' in txt:
            city, state = location.split(', ', 1)
        else:
            city, state = pd.NA, pd.NA
        return city, state, work_type
    if ', ' in txt:
        city, state = txt.split(', ', 1)
        work_type = pd.NA
        return city, state, work_type
    return pd.NA, pd.NA, pd.NA


def clean_title(text):
    """Split a job title from its '(Verified)' tag, if present."""
    if ' (' in text:
        title, verified = text.split(' (', 1)
        v = 'Verified' in verified
    elif '(' in text:
        title, verified = text.split('(', 1)
        v = 'Verified' in verified
    else:
        title = text
        v = False
    return title, v


def get_details(driver, expected_title=None):
    """Open and return the lowercase text of a job's 'About' details panel."""
    wait = WebDriverWait(driver, 5)
    job_details = wait.until(
        EC.presence_of_element_located((By.XPATH, '//div[contains(@id, "JobDetails_About")]'))
    )
    if expected_title:
        try:
            wait.until(lambda d: expected_title.lower() in job_details.text.lower())
        except TimeoutException:
            pass
    text_before = job_details.text
    try:
        button = job_details.find_element(By.XPATH, './/button[@data-testid="expandable-text-button"]')
        driver.execute_script("arguments[0].click();", button)
        try:
            WebDriverWait(driver, 3).until(lambda d: len(job_details.text) > len(text_before))
        except TimeoutException:
            logger.warning(
                "'See more' click did not appear to expand the description; "
                "returned text may be truncated. Verify the "
                "'expandable-text-button' data-testid is still current."
            )
    except NoSuchElementException:
        pass

    return job_details.text.lower()


def get_job_id_from_url(driver):
    """
    Extract LinkedIn's own job posting ID from the current URL (e.g. the
    'currentJobId=1234567890' query param). This is a much more reliable
    duplicate-detection key than title/company/location, since two
    different postings can legitimately share those. Returns None if not
    found in the URL.
    """
    match = re.search(r"currentJobId=(\d+)", driver.current_url)
    if match:
        return match.group(1)
    return None


def get_skills(description):
    """Flag which tracked skills are mentioned in an already-fetched job description."""
    sql = 'sql' in description
    excel = 'excel' in description
    python = 'python' in description
    power_bi = 'power bi' in description
    tableau = 'tableau' in description
    r = ' r ' in description or ' r, ' in description
    azure = 'azure' in description
    return sql, excel, python, power_bi, tableau, r, azure


# --- Date posted ---------------------------------------------------------

RELATIVE_DATE_RE = re.compile(
    r"(\d+)\s*(minute|hour|day|week|month|year)s?\s*ago",
    re.IGNORECASE,
)


def parse_relative_date(text, today=None):
    """
    Convert a relative date string like '3 days ago' or '2 weeks ago'
    into an actual date. Returns pd.NA if it can't be parsed.
    """
    if not text:
        return pd.NA
    if today is None:
        today = datetime.now()

    if re.search(r"\btoday\b", text, re.IGNORECASE):
        return today.date()
    if re.search(r"\byesterday\b", text, re.IGNORECASE):
        return (today - timedelta(days=1)).date()

    match = RELATIVE_DATE_RE.search(text)
    if not match:
        return pd.NA

    amount = int(match.group(1))
    unit = match.group(2).lower()

    delta_days = {
        "minute": 0,
        "hour": 0,
        "day": amount,
        "week": amount * 7,
        "month": amount * 30,
        "year": amount * 365,
    }[unit]

    return (today - timedelta(days=delta_days)).date()


def get_date_posted(driver, today=None):
    try:
        posted_el = WebDriverWait(driver, 5).until(
            lambda d: d.find_element(
                By.XPATH,
                ".//span[(contains(text(), 'ago') or contains(text(), 'Reposted'))]"
                "[not(ancestor::div[contains(@componentkey, 'SearchResultsMainContent')])]"
                "[not(ancestor::div[contains(@id, 'JobDetails_About')])]",
            )
        )
        raw_text = posted_el.text
    except (NoSuchElementException, TimeoutException):
        return pd.NA, pd.NA

    parsed_date = parse_relative_date(raw_text, today=today)
    return raw_text, parsed_date