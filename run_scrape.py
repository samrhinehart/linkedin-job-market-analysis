"""
Example entry point for running the scraper.

Credentials are pulled from environment variables — never hardcode them here.
Set LINKEDIN_EMAIL and LINKEDIN_PASSWORD before running, e.g.:
    export LINKEDIN_EMAIL="you@example.com"
    export LINKEDIN_PASSWORD="yourpassword"
"""
import os
from navigation import scrape_jobs

if __name__ == "__main__":
    email = os.environ["LINKEDIN_EMAIL"]
    password = os.environ["LINKEDIN_PASSWORD"]

    jobs_df, skills_df = scrape_jobs(
        email=email,
        password=password,
        keyword="data analyst",
        location="California",
        page_limit=5,
    )

    jobs_df.to_csv("jobs.csv", index=False)
    skills_df.to_csv("skills.csv", index=False)
    print(f"Scraped {len(jobs_df)} postings.")
