"""
Removes duplicate rows from jobs.csv / skills.csv, if any slipped through.

Run this any time as a safety net -- e.g. after a long unattended scrape,
or if you've merged CSVs from separate runs together manually.

Usage:
    python3 dedupe_csv.py
"""
import pandas as pd

JOBS_CSV = "jobs.csv"
SKILLS_CSV = "skills.csv"


def main():
    jobs = pd.read_csv(JOBS_CSV)
    skills = pd.read_csv(SKILLS_CSV)

    before = len(jobs)

    # Prefer deduping on LinkedIn's own job ID where we have it (most reliable).
    has_id = jobs["linkedin_job_id"].notna()
    with_id = jobs[has_id].drop_duplicates(subset="linkedin_job_id", keep="first")
    without_id = jobs[~has_id].drop_duplicates(
        subset=["title", "company", "city", "state"], keep="first"
    )
    jobs_deduped = pd.concat([with_id, without_id], ignore_index=True)

    removed = before - len(jobs_deduped)

    # Keep skills rows in sync with whichever job_ids survived
    skills_deduped = skills[skills["job_id"].isin(jobs_deduped["job_id"])]

    jobs_deduped.to_csv(JOBS_CSV, index=False)
    skills_deduped.to_csv(SKILLS_CSV, index=False)

    print(f"Removed {removed} duplicate row(s) out of {before} total.")
    print(f"{len(jobs_deduped)} unique postings remain.")


if __name__ == "__main__":
    main()