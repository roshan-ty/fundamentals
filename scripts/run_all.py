#!/usr/bin/env python3
"""
Master Data Pipeline Wrapper — Bulls & Bears Fundamentals

Executes the entire backend data pipeline cleanly in sequence with a single
command. Regenerates all 5 production JSON files in public/data/:

  1. calendar.json          (scripts/calendar_scraper.py)
  2. news.json              (scripts/news_scraper.py)
  3. master_bias.json       (scripts/build_fundamental_bias.py)
  4. cftc_report.json       (scripts/build_cftc_data.py)
  5. ai_insights.json       (scripts/generate_ai_notes.py)

Usage:
  python scripts/run_all.py             # default: fixture-safe offline run
  python scripts/run_all.py --live      # try live scrapes, fall back to fixture
"""

import subprocess
import sys


# Network scrapers that may fail when Forex Factory is Cloudflare-blocked.
# In --live mode they are retried with --fixture before the pipeline aborts.
NETWORK_SCRAPERS = {"calendar_scraper.py", "news_scraper.py"}


def run_step(script_name, extra_args=None):
    print(f"==> Running {script_name}...")
    args = [sys.executable, f"scripts/{script_name}"]
    if extra_args:
        args.extend(extra_args)
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] Error running {script_name}:\n{result.stderr}")
        # Live scrape failed (e.g. Cloudflare 403) -> fall back to fixture data
        # so the 24/7 pipeline never aborts.
        if script_name in NETWORK_SCRAPERS and "--fixture" not in (extra_args or []):
            print(f"[FALLBACK] {script_name} failed live fetch; retrying with "
                  f"--fixture so production data remains available.")
            retry_args = ["--fixture"]
            retry = subprocess.run(
                [sys.executable, f"scripts/{script_name}"] + retry_args,
                capture_output=True, text=True,
            )
            if retry.returncode == 0:
                print(f"[OK] Finished {script_name} (fixture fallback)\n")
                return True
            print(f"[ERROR] Fixture fallback also failed:\n{retry.stderr}")
        return False
    print(f"[OK] Finished {script_name}\n")
    return True


if __name__ == "__main__":
    # --live: attempt live Forex Factory/News scrapes first (fall back to
    # fixture if the site is Cloudflare-blocked or unreachable). Used by the
    # 24/7 GitHub Actions workflow.
    live_mode = "--live" in sys.argv

    print("Starting Bulls & Bears Fundamentals Master Data Pipeline...\n")

    steps = [
        ("calendar_scraper.py", None if live_mode else ["--fixture"]),
        ("news_scraper.py", None if live_mode else ["--fixture"]),
        ("build_fundamental_bias.py", None),
        ("build_cftc_data.py", None),
        ("generate_ai_notes.py", None),
    ]

    for step, extra in steps:
        if not run_step(step, extra):
            print("Pipeline aborted due to errors.")
            sys.exit(1)

    print("All production datasets regenerated successfully in public/data/!")
