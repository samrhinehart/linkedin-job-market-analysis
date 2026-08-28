# LinkedIn Job Market Analysis: Data Roles & Skill Demand

**Status: In Progress** — scraping and data pipeline complete; SQL analysis in progress.

## Overview
This project scrapes live LinkedIn job listings for data-related roles (Data Analyst, Data Scientist, Data Engineer, etc.) and analyzes which skills are associated with higher compensation. The goal is to answer:

> **Which skills carry the biggest salary premium for entry-level data roles right now, and does that premium hold across job titles (Analyst vs. Scientist vs. Engineer)?**

## What's built so far
- **Scraper** (`scraper_funs.py`): Selenium + BeautifulSoup pipeline that logs into LinkedIn, searches for data-related roles by keyword and location, and paginates through results, extracting title, company, location, work type, and full job description text.
- **Parsing / cleaning**:
  - Regex-based salary extractor that handles hourly vs. annual pay, ranges vs. single values, and filters out false positives (e.g., 401(k), percentages, headcount figures)
  - Title parser that separates job title from "Verified" status
  - Location parser that splits city, state, and work type (remote/hybrid/on-site)
- **Output**: two structured tables —
  - `jobs`: one row per posting (title, company, location, work type, salary range, raw description)
  - `skills`: one row per posting, boolean flags for SQL, Excel, Python, Power BI, Tableau, R, Azure

## Next steps
- [ ] Extract seniority and date posted for more thorough queries
- [ ] Load `jobs` and `skills` into a SQL database
- [ ] Write queries to compare average salary by skill, controlling for job title category
- [ ] Explore skill co-occurrence (e.g., SQL + Python vs. SQL alone)
- [ ] Expand scraping beyond California to get geographic variation
- [ ] Write up findings

## Tech stack
Python, Selenium, BeautifulSoup, pandas, regex, SQL (upcoming)

## Note on data
Due to LinkedIn's Terms of Service, raw scraped job data is not included in this repository. This repo showcases the scraping/parsing methodology and code only. The project is for personal educational purposes.

## Files
- `scraper_funs.py` — scraping, parsing, and salary-extraction functions
- more coming as the SQL analysis is completed
