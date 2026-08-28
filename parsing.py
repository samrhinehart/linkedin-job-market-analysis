"""
Cleans and parses raw text pulled from job cards and job detail panels:
locations, job titles, and skill mentions.
"""
import time
import pandas as pd
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By

from salary_extraction import get_salary  # noqa: F401  (re-exported for convenience)


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
    try:
        button = job_details.find_element(By.XPATH, './/button[@data-testid="expandable-text-button"]')
        driver.execute_script("arguments[0].click();", button)
    except NoSuchElementException:
        pass
    time.sleep(.3)
    return job_details.text.lower()


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
