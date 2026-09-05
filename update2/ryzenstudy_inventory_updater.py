#!/usr/bin/env python3
"""
ryzenstudy_inventory_updater.py
-------------------------------
Keeps ryzenstudy_paper_inventory.csv in sync with ryzenstudy.com's sitemap.

What it does:
  1. Fetches https://ryzenstudy.com/sitemap.xml live
  2. Extracts every /papers/* URL and parses it into
     (course, semester, academic_year, subject_slug)
  3. Diffs against your existing inventory CSV:
        - NEW papers   (in sitemap, not in CSV)   -> appended
        - GONE papers  (in CSV, not in sitemap)   -> reported, kept but flagged
  4. Writes the refreshed CSV (sorted) and a diff report

Usage:
  python3 ryzenstudy_inventory_updater.py                    # report only (no changes)
  python3 ryzenstudy_inventory_updater.py --write            # update the CSV in place
  python3 ryzenstudy_inventory_updater.py --csv my.csv --write

Run it: whenever you re-run the PDF scraper (e.g., after each AKTU exam cycle),
or weekly from a scheduled job. The sitemap is the site's own freshest index,
so if ryzenstudy adds papers, this picks them up automatically.
"""
import argparse
import csv
import re
import sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen

SITEMAP = "https://ryzenstudy.com/sitemap.xml"
PAPER_RE = re.compile(
    r"https://ryzenstudy\.com/papers/aktu-(btech|bca|mca|bpharm|mba|bba)-sem-(\d)-(.+?)-(\d{4}-\d{2})$"
)
FIELDS = ["course", "semester", "academic_year", "subject_slug", "url"]


def fetch_sitemap_papers():
    req = Request(SITEMAP, headers={"User-Agent": "pyq-inventory-sync/1.0"})
    with urlopen(req, timeout=30) as r:
        raw = r.read().decode("utf-8", "ignore")
    locs = re.findall(r"<loc>([^<]+)</loc>", raw)
    rows, lastmod = [], None
    lm = re.findall(r"<loc>(https://ryzenstudy\.com/?)</loc>\s*<lastmod>([^<]+)</lastmod>", raw)
    if lm:
        lastmod = lm[0][1]
    for u in locs:
        m = PAPER_RE.match(u)
        if m:
            course, sem, slug, year = m.groups()
            rows.append({
                "course": course.upper(),
                "semester": f"Sem {sem}",
                "academic_year": year,
                "subject_slug": slug,
                "url": u,
            })
    return rows, lastmod


def load_existing(path):
    try:
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="ryzenstudy_paper_inventory.csv")
    ap.add_argument("--write", action="store_true", help="write refreshed CSV (default: report only)")
    args = ap.parse_args()

    live, sitemap_lastmod = fetch_sitemap_papers()
    existing = load_existing(args.csv)
    live_urls = {r["url"] for r in live}
    old_urls = {r["url"] for r in existing}

    added = [r for r in live if r["url"] not in old_urls]
    removed = [u for u in sorted(old_urls - live_urls)]

    print(f"[i] sitemap lastmod (homepage) : {sitemap_lastmod}")
    print(f"[i] live paper URLs in sitemap : {len(live)}")
    print(f"[i] existing CSV rows          : {len(existing)}")
    print(f"[i] NEW since last sync        : {len(added)}")
    print(f"[i] removed from sitemap       : {len(removed)}")
    for r in added[:10]:
        print(f"    + {r['course']:7} {r['semester']:7} {r['academic_year']:8} {r['subject_slug']}")
    for u in removed[:10]:
        print(f"    - {u}")
    if len(added) > 10 or len(removed) > 10:
        print(f"    ... ({max(0, len(added)-10)} more added, {max(0, len(removed)-10)} more removed)")

    if not args.write:
        print("[i] report only - rerun with --write to update the CSV")
        return

    merged = [r for r in existing if r["url"] in live_urls] + added
    merged.sort(key=lambda r: (r["course"], r["semester"], r["academic_year"], r["subject_slug"]))
    with open(args.csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(merged)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"[i] CSV updated: {len(merged)} rows -> {args.csv} (at {stamp})")


if __name__ == "__main__":
    sys.exit(main())
