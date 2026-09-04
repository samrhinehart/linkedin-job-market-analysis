"""
Entry point for running the scraper toward a larger target (e.g. ~2000
postings), unattended.

Credentials are pulled from environment variables — never hardcode them.
Set these before running:
    export LINKEDIN_EMAIL="you@example.com"
    export LINKEDIN_PASSWORD="yourpassword"

Because a single LinkedIn search caps out around ~1000 results, this loops
across several (keyword, location) combinations to reach a larger total.
Progress is saved to jobs.csv / skills.csv after every job, so it's safe
to stop and resume this later, and safe to leave running while you're away.
Check scrape_log.txt for progress and any errors while it runs.
"""
import os
from navigation import scrape_many

if __name__ == "__main__":
    email = os.environ["LINKEDIN_EMAIL"]
    password = os.environ["LINKEDIN_PASSWORD"]

    # Add/adjust combinations here to widen coverage. Duplicate postings
    # across searches are automatically skipped.
    searches = [
        ("data analyst", "California"),
        ("data scientist", "California"),
        ("data engineer", "California"),
        ("business analyst", "California"),
        ("data analyst", "Remote"),
    ]

    jobs_df, skills_df = scrape_many(
        email=email,
        password=password,
        searches=searches,
        target_total=25,
        jobs_csv_path="jobs.csv",
        skills_csv_path="skills.csv",
    )

    print(f"Done. {len(jobs_df)} total postings saved to jobs.csv / skills.csv.")