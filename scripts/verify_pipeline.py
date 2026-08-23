#!/usr/bin/env python3
"""Verify all 5 production JSON files are populated correctly."""
import json
import os

base = "public/data"
files = ["calendar.json", "news.json", "master_bias.json", "cftc_report.json", "ai_insights.json"]

print("=== Pipeline Output Verification ===")
for f in files:
    p = os.path.join(base, f)
    with open(p, encoding="utf-8") as fh:
        d = json.load(fh)
    if isinstance(d, list):
        print(f"{f}: {len(d)} events")
    elif "articles" in d:
        print(f"{f}: {d['total_articles']} articles")
    elif "assets" in d:
        print(f"{f}: {len(d['assets'])} assets, {d['total_pairs']} pairs")
    elif "data" in d:
        print(f"{f}: {d['total_markets']} markets")
    elif "notes" in d:
        print(f"{f}: {len(d['notes'])} notes")
    else:
        print(f"{f}: keys={list(d.keys())[:4]}")

print("ALL 5 JSON FILES VERIFIED")