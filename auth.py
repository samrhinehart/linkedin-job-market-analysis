"""
Handles logging into LinkedIn with Selenium.

Credentials should be passed in from environment variables or a local,
gitignored file — never hardcoded here.
"""
import time
from selenium import webdriver
from selenium.webdriver.common.by import By


def login(user_email="", password=""):
    """Log into LinkedIn and return the active driver session."""
    driver = webdriver.Chrome()
    driver.get("https://www.linkedin.com/login")
    time.sleep(1)

    emails = driver.find_elements(By.CSS_SELECTOR, "input[type='email']")
    username = [e for e in emails if e.is_displayed()][0]
    username.send_keys(user_email)

    passwords = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
    pword = [p for p in passwords if p.is_displayed()][0]
    pword.send_keys(password)

    # NOTE: indexing into all page buttons by position (buttons[5]) is brittle —
    # if LinkedIn changes their login page layout, this index will silently break.
    # Worth revisiting with a more specific selector (e.g. button[type="submit"]).
    buttons = driver.find_elements(By.XPATH, "//button")
    buttons[5].click()

    return driver
