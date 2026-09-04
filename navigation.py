"""
Navigates LinkedIn's job search UI and drives the main scrape loop.

Designed to run unattended for a long stretch (e.g., overnight) to collect
a few thousand postings:
  - progress is saved to CSV after every job
  - already-scraped jobs are automatically skipped if you restart the script
  - one bad job card or a page-level error is logged and skipped rather
    than crashing the whole run
  - if the browser session itself crashes, it logs back in and resumes
    (up to a limited number of restarts)
  - a single LinkedIn search caps out around ~1000 results, so this loops
    across multiple (keyword, location) searches to reach a larger target
"""
import csv
import logging
import os
import random
import time

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from auth import login
from parsing import clean_title, get_date_posted, get_details, get_job_id_from_url, get_skills, split_loc
from salary_extraction import get_salary
from seniority_extraction import get_seniority_level, get_years_experience

logging.basicConfig(
    filename="scrape_log.txt",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


JOBS_FIELDS = [
    "job_id", "linkedin_job_id", "title", "company", "verified_job", "city", "state", "work_type",
    "salary_minimum", "salary_maximum", "seniority_level", "date_posted",
]

SKILLS_FIELDS = [
    "job_id", "sql", "excel", "python", "power_bi", "tableau", "r", "azure",
]


def _load_seen_keys(jobs_csv_path):
    """
    Read an existing jobs.csv (if any) and return the set of already-scraped
    keys, plus the next job_id to use. Prefers LinkedIn's own job ID as the
    key (most reliable); falls back to (title, company, city, state) for
    older rows that don't have one.
    This is what makes restarting after a crash safe: previously scraped
    jobs get skipped instead of duplicated.
    """
    seen = set()
    next_id = 1
    if os.path.exists(jobs_csv_path):
        existing = pd.read_csv(jobs_csv_path)
        for _, row in existing.iterrows():
            lid = row.get("linkedin_job_id")
            if pd.notna(lid):
                seen.add(str(lid))
            else:
                seen.add((row.get("title"), row.get("company"), row.get("city"), row.get("state")))
        if len(existing) > 0:
            next_id = int(existing["job_id"].max()) + 1
    return seen, next_id


def _append_row(path, fieldnames, row):
    """Append a single row dict to a CSV, writing the header only if the file is new."""
    file_exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def dismiss_popups(driver, timeout=3):
    """
    Best-effort dismissal of common post-login LinkedIn popups/modals
    (notification permission prompts, welcome interstitials, chat bubbles,
    etc.) that can sit on top of the page and block clicks on the
    underlying content until manually closed. Safe to call even when
    nothing is actually there -- it just does nothing in that case.
    """
    dismiss_selectors = [
        "//button[contains(@aria-label, 'Dismiss')]",
        "//button[contains(@aria-label, 'Close')]",
        "//button[contains(@class, 'artdeco-modal__dismiss')]",
        "//icon[contains(@class, 'close-icon')]/..",
    ]
    for selector in dismiss_selectors:
        try:
            btn = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, selector))
            )
            btn.click()
            time.sleep(0.5)
            logger.info(f"Dismissed a popup using selector: {selector}")
        except (TimeoutException, NoSuchElementException):
            continue


def jobs_page(driver, keyword, location='California'):
    """Navigate to LinkedIn's Jobs tab and run a search for keyword + location."""
    dismiss_popups(driver)
    try:
        jobs = driver.find_element(By.XPATH, "//a[contains(@aria-label, 'Jobs')]")
        jobs.click()
    except ElementClickInterceptedException:
        # Something is still overlaying the page -- try once more to clear it, then retry the click.
        logger.warning("Click on Jobs tab was intercepted by a popup; retrying after dismissal.")
        dismiss_popups(driver)
        jobs = driver.find_element(By.XPATH, "//a[contains(@aria-label, 'Jobs')]")
        jobs.click()

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


def _scrape_one_search(driver, keyword, location, seen_keys, job_id_counter,
                        jobs_csv_path, skills_csv_path, page_limit,
                        target_total, running_total):
    """
    Scrape one (keyword, location) search, appending each row to CSV as it
    goes. Returns the updated (job_id_counter, running_total).
    """
    driver = jobs_page(driver, keyword, location)
    page = 1

    while page <= page_limit and running_total < target_total:
        time.sleep(random.uniform(2.5, 4.5))  # jitter to look less bot-like

        try:
            container = driver.find_element(By.XPATH, "//div[@componentkey='SearchResultsMainContent']")
            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", container)
        except NoSuchElementException:
            logger.warning(f"Results container not found on page {page} for '{keyword}' in '{location}'; stopping this search.")
            break

        cards = driver.find_elements(
            By.XPATH,
            "//div[contains(@componentkey,'SearchResultsMainContent')]//div[@role='button' and not(@aria-expanded)]"
        )

        for card in cards:
            if running_total >= target_total:
                break
            try:
                html = card.get_attribute("innerHTML")
                soup = BeautifulSoup(html, "lxml")
                for hidden in soup.find_all(attrs={"aria-hidden": "true"}):
                    hidden.decompose()
                text = [p.get_text(strip=True) for p in soup.find_all("p")]

                title, verified = clean_title(text[0])
                company = text[1]
                city, state, work_center = split_loc(text[2])

                fallback_key = (title, company, city, state)
                if fallback_key in seen_keys:
                    continue  # fast pre-click skip, avoids wasting a click on an obvious repeat

                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", card)
                card.click()

                description = get_details(driver, title)
                linkedin_job_id = get_job_id_from_url(driver)

                # A second, more reliable check now that we have LinkedIn's own ID
                # (catches reposts/slightly-reformatted titles the fast check missed)
                id_key = linkedin_job_id if linkedin_job_id else fallback_key
                if id_key in seen_keys:
                    logger.info(f"Skipping duplicate caught by LinkedIn job ID: {linkedin_job_id}")
                    continue

                sal_min, sal_max = get_salary(description)
                sql, excel, python, power_bi, tableau, r, azure = get_skills(description)
                years_min, years_max = get_years_experience(description)
                seniority = get_seniority_level(description, years_min)
                date_raw, date_parsed = get_date_posted(driver)

                job_row = {
                    "job_id": job_id_counter,
                    "linkedin_job_id": linkedin_job_id,
                    "title": title,
                    "company": company,
                    "verified_job": verified,
                    "city": city,
                    "state": state,
                    "work_type": work_center,
                    "salary_minimum": sal_min,
                    "salary_maximum": sal_max,
                    "seniority_level": seniority,
                    "date_posted": date_parsed,
                }
                skills_row = {
                    "job_id": job_id_counter,
                    "sql": sql, "excel": excel, "python": python,
                    "power_bi": power_bi, "tableau": tableau, "r": r, "azure": azure,
                }

                _append_row(jobs_csv_path, JOBS_FIELDS, job_row)
                _append_row(skills_csv_path, SKILLS_FIELDS, skills_row)

                seen_keys.add(fallback_key)
                seen_keys.add(id_key)
                job_id_counter += 1
                running_total += 1

                if running_total % 25 == 0:
                    logger.info(f"Progress: {running_total} jobs scraped so far.")

            except (StaleElementReferenceException, TimeoutException, IndexError) as e:
                logger.warning(f"Skipped one job card due to a page/timing error: {e}")
                continue
            except Exception as e:
                # Catch-all so one unexpected bad card can never kill an unattended run.
                logger.error(f"Unexpected error on a job card, skipping it: {e}")
                continue

        try:
            next_button = driver.find_element(By.XPATH, '//button[contains(@data-testid, "next-button")]')
            driver.execute_script("arguments[0].click();", next_button)
            page += 1
            time.sleep(random.uniform(2, 3))
        except NoSuchElementException:
            break

    return job_id_counter, running_total


def scrape_many(email, password, searches, target_total=2000, page_limit=np.inf,
                 jobs_csv_path="jobs.csv", skills_csv_path="skills.csv",
                 max_driver_restarts=3):
    """
    Scrape across multiple (keyword, location) search combinations until
    target_total postings are collected or all searches are exhausted.

    Built for unattended runs: saves each row to CSV immediately, skips
    duplicates/previously-scraped jobs if restarted, logs progress and
    errors to scrape_log.txt, and restarts the browser session (up to
    max_driver_restarts times) if it crashes partway through.

    Parameters
    ----------
    searches : list of (keyword, location) tuples, e.g.
        [("data analyst", "California"), ("data scientist", "California"),
         ("business analyst", "California")]
    target_total : int
        Stop once this many total rows exist in jobs_csv_path (across all
        searches, including any scraped in a previous run).
    """
    seen_keys, job_id_counter = _load_seen_keys(jobs_csv_path)
    running_total = len(seen_keys)
    if running_total > 0:
        logger.info(f"Resuming: found {running_total} jobs already in {jobs_csv_path}.")

    driver = None
    restarts = 0
    search_idx = 0

    try:
        while search_idx < len(searches) and running_total < target_total:
            keyword, location = searches[search_idx]
            try:
                if driver is None:
                    logger.info("Logging in...")
                    driver = login(email, password)
                    time.sleep(3)

                logger.info(f"Searching '{keyword}' in '{location}' (total so far: {running_total}/{target_total})")
                job_id_counter, running_total = _scrape_one_search(
                    driver, keyword, location, seen_keys, job_id_counter,
                    jobs_csv_path, skills_csv_path, page_limit, target_total, running_total
                )
                search_idx += 1  # only move to the next search once this one finishes cleanly

            except WebDriverException as e:
                restarts += 1
                logger.error(f"Browser session crashed ({e}). Restart attempt {restarts}/{max_driver_restarts}.")
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = None
                if restarts > max_driver_restarts:
                    logger.error("Max restarts exceeded. Stopping; progress so far is safely saved in the CSVs.")
                    break
                time.sleep(10)
                # search_idx is NOT incremented, so the same search resumes (skipping
                # already-seen jobs) once the driver logs back in.
    except KeyboardInterrupt:
        # Manual stop (e.g. Jupyter interrupt / Ctrl+C). Everything scraped so far
        # is already saved to CSV -- just close the browser cleanly and return it.
        logger.info(f"Stopped manually by user at {running_total} jobs. Progress is saved.")
        print(f"Stopped manually. {running_total} jobs saved to {jobs_csv_path} so far.")

    if driver is not None:
        driver.quit()

    logger.info(f"Finished. Total jobs in {jobs_csv_path}: {running_total}")

    if os.path.exists(jobs_csv_path):
        return pd.read_csv(jobs_csv_path), pd.read_csv(skills_csv_path)
    return pd.DataFrame(columns=JOBS_FIELDS), pd.DataFrame(columns=SKILLS_FIELDS)


def scrape_jobs(email, password, keyword, location='California', page_limit=np.inf):
    """
    Backward-compatible single-search wrapper around scrape_many, for quick
    tests of one keyword/location combo. Still saves incrementally to
    jobs.csv/skills.csv in the current folder.
    """
    return scrape_many(
        email, password,
        searches=[(keyword, location)],
        target_total=np.inf,
        page_limit=page_limit,
    )