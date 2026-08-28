"""
Navigates LinkedIn's job search UI and drives the main scrape loop:
searching by keyword/location, paging through results, and collecting
one row per job posting into the jobs/skills tables.
"""
import time
import numpy as np
import pandas as pd
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException

from auth import login
from parsing import split_loc, clean_title, get_details, get_skills
from salary_extraction import get_salary


def jobs_page(driver, keyword, location='California'):
    """Navigate to LinkedIn's Jobs tab and run a search for keyword + location."""
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


def scrape_jobs(email, password, keyword, location='California', page_limit=np.inf):
    """Log in, search, and scrape job postings into (jobs_df, skills_df)."""
    driver = login(email, password)
    time.sleep(3)
    driver = jobs_page(driver, keyword, location)

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

            title, verified = clean_title(text[0])
            company = text[1]
            city, state, work_center = split_loc(text[2])

            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});",
                card
            )
            card.click()

            # Fetch the job's description once, then reuse it for both
            # salary extraction and skill detection (previously fetched twice).
            description = get_details(driver, title)
            sal_min, sal_max = get_salary(description)
            sql, excel, python, power_bi, tableau, r, azure = get_skills(description)

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
