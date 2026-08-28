from selenium import webdriver
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import time
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
from selenium.webdriver.common.keys import Keys
import scraper_funs as sf
import re
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import TimeoutException
import numpy as np
import importlib

def split_loc(txt):
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
    else:
        return pd.NA, pd.NA, pd.NA

def clean_sal(text):
    sal_min, sal_max = text.split("-")
    sal_min = re.sub(r'[^0-9]+', '', sal_min)
    sal_max = re.sub(r'[^0-9]+', '', sal_max)

    sal_min = int(sal_min) * 1000
    sal_max = int(sal_max) * 1000
    return sal_min, sal_max

def clean_title(text):
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

def login(user_email="", password=""):
    driver = webdriver.Chrome()

    driver.get("https://www.linkedin.com/login")

    time.sleep(1)

    # wait until username box appears
    emails = driver.find_elements(By.CSS_SELECTOR, "input[type='email']")
    username = [e for e in emails if e.is_displayed()][0]
    username.send_keys(user_email)

    passwords = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
    pword = [p for p in passwords if p.is_displayed()][0]
    pword.send_keys(password)

    buttons = driver.find_elements(By.XPATH, "//button")

    buttons[5].click()

    return driver

def jobs_page(driver, keyword, location='California'):
    jobs = driver.find_element(
        By.XPATH,
        "//a[contains(@aria-label, 'Jobs')]"
    )
    jobs.click()

    job_src = driver.page_source

    soup = BeautifulSoup(job_src, 'lxml')

    search_box = WebDriverWait(driver, 5).until(
        EC.presence_of_element_located(
            (By.XPATH, "//input[contains(@componentkey,'jobSearchBox')]")
        )
    )
    search_box.clear()
    search_box.send_keys(keyword)
    search_box.send_keys(Keys.ENTER)

    location_button = WebDriverWait(driver, 5).until(
        EC.presence_of_element_located(
            (By.XPATH, "//div[@role = 'button' and .//div[contains(@aria-label, 'Location')]]")
        )
    )
    location_button.click()
    location_box = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable(
            (By.XPATH, "//div[contains(@componentkey,'LocationTypeahead')]")
        )
    )
    location_box.click() 
    clear_button = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable(
            (By.XPATH, "//button[contains(@aria-label, 'Clear location')]")
        )
    )
    clear_button.click()
    location_box.send_keys(location)

    loc = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable(
            (By.XPATH, f"//a[contains(@href,'JOB_SEARCH_PAGE_LOCATION_AUTOCOMPLETE')][.//span[contains(text(), '{location}')]]")
        )
    )
    href = loc.get_attribute("href")
    driver.get(href)
    return driver

def scrape_jobs(email, password, keyword, location='California', page_limit=np.inf):
    driver = login(email, password)
    time.sleep(3)
    driver = jobs_page(driver, keyword, location)

    wait = WebDriverWait(driver, 5)
    all_jobs = []
    all_skills = []
    job_id = 1 
    page = 1
    while page <= page_limit:
        time.sleep(3)

        container = driver.find_element(By.XPATH, "//div[@componentkey='SearchResultsMainContent']")
        driver.execute_script(
            "arguments[0].scrollTop = arguments[0].scrollHeight;",
            container
        )

        cards = driver.find_elements(
            By.XPATH,
            "//div[contains(@componentkey,'SearchResultsMainContent')]//div[@role='button' and not(@aria-expanded)]"
        )

        for card in cards:
            html = card.get_attribute("innerHTML")
            soup = BeautifulSoup(html, "lxml")
            for hidden in soup.find_all(attrs={"aria-hidden": "true"}):
                hidden.decompose()

            text = [p.get_text(strip=True) for p in soup.find_all("p")]

            title = text[0]
            title, verified = sf.clean_title(title)
            company = text[1]
            location = text[2]
            city, state, work_center = sf.split_loc(location)

            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});",
                card
            )
            card.click()
            # time.sleep(0.5)

            description = get_details(driver, title)
            sal_min, sal_max = get_salary(description)
            sql, excel, python, power_bi, tableau, r, azure = get_skills(driver)

            all_jobs.append({
                "job_id": job_id,
                "title": title,
                "company": company,
                "verified_job": verified,
                "city": city,
                "state": state,
                "work_type": work_center,
                "salary_minimum": sal_min,
                "salary_maximum": sal_max,
                "raw_description": description
            })

            all_skills.append({
                "job_id": job_id,
                "sql": sql,
                "excel": excel,
                "python": python,
                "power_bi": power_bi,
                "tableau": tableau,
                "r": r,
                "azure": azure
            })

            job_id += 1

        try:
            next_button = driver.find_element(By.XPATH, '//button[contains(@data-testid, "next-button")]')
            driver.execute_script("arguments[0].click();", next_button)
            page += 1
            time.sleep(2)
        except NoSuchElementException:
            break

    return pd.DataFrame(all_jobs), pd.DataFrame(all_skills)

def get_skills(driver):
    description = get_details(driver)
    SQL = 'sql' in description
    excel = 'excel' in description
    python = 'python' in description
    power_bi = 'power bi' in description
    tableau = 'tableau' in description
    r = ' r ' in description or ' r, ' in description
    azure = 'azure' in description

    return SQL, excel, python, power_bi, tableau, r, azure

def get_details(driver, expected_title=None):
    wait = WebDriverWait(driver, 5)
    job_details = wait.until(
        EC.presence_of_element_located((By.XPATH, '//div[contains(@id, "JobDetails_About")]'))
    )
    if expected_title:
        try:
            wait.until(lambda d: expected_title.lower() in job_details.text.lower())
        except TimeoutException:
            pass
    try:
        button = job_details.find_element(By.XPATH, './/button[@data-testid="expandable-text-button"]')
        driver.execute_script("arguments[0].click();", button)
    except NoSuchElementException:
        pass
    time.sleep(.3)
    description = job_details.text.lower()
    return description


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

RETIREMENT_PLAN_RE = re.compile(
    r"\b40[13]\s*\(?\s*k\s*\)?\b|\b40[13]\s*\(?\s*b\s*\)?\b|\b457\s*\(?\s*b\s*\)?\b",
    re.IGNORECASE,
)


def get_salary(description):
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
