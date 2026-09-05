#!/usr/bin/env python3
"""
AKTU PYQ Scraper v2  -  bulk downloader for ryzenstudy.com question papers
==========================================================================
WHAT IT DOES
  1. Reads https://ryzenstudy.com/sitemap.xml, keeps all /papers/* URLs.
  2. Processes courses in priority order: B.Tech -> B.Pharm -> MCA
     (BBA/BCA are skipped by default; use --courses to include them).
  3. For each paper page (server-rendered), extracts:
        - the self-hosted PDF path  (/uploads/*.pdf)
        - metadata: paperCode, paperName, course, semester, academic year
  4. Saves every PDF TWICE, with a database-friendly filename:
        aktu-pyq/structured/{Course}/Sem-{NN}/{year}/{Course}__Sem{NN}__{year}__{CODE}__{subject}.pdf
        aktu-pyq/unstructured/{same filename}.pdf          <- flat, no subfolders

  FILENAME CONVENTION (fields separated by double underscore "__",
  words inside a field separated by single hyphen "-"):
        BTech__Sem05__2022-23__KEC055__electronics-switching.pdf
         |       |        |       |            |
       course  semester  year  subject     subject name
                        (acad)   code       (slug)

  Parse rule for your database:  split on "__" ->
        [course, semester, academic_year, subject_code, subject_slug]

POLITENESS / SAFETY
  - Sequential requests, default delay 1.2s + random jitter
  - Descriptive User-Agent, no auth bypass, public pages only
  - Resume-safe: rerun anytime; already-downloaded papers are skipped
  - A manifest CSV records every file with status and both paths

USAGE
  python3 ryzenstudy_pyq_scraper.py                    # full run: BTech, BPharm, MCA
  python3 ryzenstudy_pyq_scraper.py --limit 5          # quick test
  python3 ryzenstudy_pyq_scraper.py --course btech     # single course
  python3 ryzenstudy_pyq_scraper.py --courses btech,bpharm,mca,bba,bca
  python3 ryzenstudy_pyq_scraper.py --delay 0.6        # faster (be reasonable)
  python3 ryzenstudy_pyq_scraper.py --out ./aktu-pyq   # output folder (default)

FULL RUN ESTIMATE: ~1,445 papers, 2 requests each, ~80-100 minutes,
~150-200 MB. Progress prints every file; press Ctrl+C to pause,
rerun the same command to resume where it stopped.
"""
import argparse
import csv
import os
import random
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests

BASE = "https://ryzenstudy.com"
SITEMAP = BASE + "/sitemap.xml"
HEADERS = {
    "User-Agent": "AKTU-PYQ-archiver/2.0 (personal educational use; respectful crawl)",
    "Accept-Language": "en",
}
COURSE_LABELS = {
    "btech": "BTech",
    "bpharm": "BPharm",
    "mca": "MCA",
    "bba": "BBA",
    "bca": "BCA",
}
PAPER_RE = re.compile(r"/papers/aktu-(btech|bca|mca|bpharm|mba|bba)-sem-(\d)-(.+?)-(\d{4}-\d{2})$")
PDF_RE = re.compile(r'href="(/uploads/[^"]+?\.pdf)"')
CODE_RE = re.compile(r'"paperCode\\?":\\?"([^"\\]+)\\?"')
NAME_RE = re.compile(r'"paperName\\?":\\?"([^"\\]+)\\?"')

MANIFEST_FIELDS = ["course", "semester", "academic_year", "paper_code", "paper_name",
                   "paper_url", "pdf_url", "structured_path", "unstructured_path",
                   "status", "downloaded_at"]


def log(msg):
    print(msg, flush=True)


def safe_name(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(s)).strip("_")[:120]


def build_filename(course, sem, year, code, slug):
    """Database-friendly filename: fields split by '__'."""
    return "{}__Sem{:02d}__{}__{}__{}.pdf".format(
        course, int(sem), year, safe_name(code or "UNKNOWN"), safe_name(slug))


def get_paper_urls(session, courses):
    r = session.get(SITEMAP, timeout=30)
    r.raise_for_status()
    locs = re.findall(r"<loc>([^<]+)</loc>", r.text)
    by_course = {c: [] for c in courses}
    for u in locs:
        m = PAPER_RE.search(u)
        if m and m.group(1) in by_course:
            by_course[m.group(1)].append(u)
    # priority order preserved: courses list order
    ordered = []
    for c in courses:
        ordered.extend(sorted(by_course[c]))
    return ordered


def already_done(manifest_path):
    done = set()
    if os.path.exists(manifest_path):
        with open(manifest_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["status"] in ("OK", "SKIP"):
                    done.add(row["paper_url"])
    return done


def append_manifest(manifest_path, row):
    newfile = not os.path.exists(manifest_path)
    with open(manifest_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        if newfile:
            w.writeheader()
        w.writerow(row)


def main():
    ap = argparse.ArgumentParser(description="Polite AKTU PYQ bulk downloader (ryzenstudy.com)")
    ap.add_argument("--out", default="./aktu-pyq", help="output root folder (default: ./aktu-pyq)")
    ap.add_argument("--manifest", default="./aktu-pyq_manifest.csv",
                    help="manifest CSV path (default: next to output folder)")
    ap.add_argument("--limit", type=int, default=0, help="process only first N papers (0 = all)")
    ap.add_argument("--delay", type=float, default=1.2, help="seconds between requests")
    ap.add_argument("--courses", default="btech,bpharm,mca",
                    help="comma list in priority order (default: btech,bpharm,mca)")
    args = ap.parse_args()

    courses = [c.strip().lower() for c in args.courses.split(",") if c.strip().lower() in COURSE_LABELS]
    os.makedirs(os.path.join(args.out, "structured"), exist_ok=True)
    os.makedirs(os.path.join(args.out, "unstructured"), exist_ok=True)

    session = requests.Session()
    session.headers.update(HEADERS)

    log(f"[i] fetching sitemap ...")
    papers = get_paper_urls(session, courses)
    if args.limit:
        papers = papers[: args.limit]
    total = len(papers)
    log(f"[i] {total} paper pages queued (courses: {', '.join(c.upper() for c in courses)})")

    done = already_done(args.manifest)
    ok = fail = skip = 0
    t0 = time.time()

    for i, url in enumerate(papers, 1):
        if url in done:
            skip += 1
            continue
        m = PAPER_RE.search(url)
        course_key, sem, slug, year = m.groups()
        course = COURSE_LABELS[course_key]

        try:
            # 1) fetch paper page
            time.sleep(args.delay + random.uniform(0, 0.4))
            r = session.get(url, timeout=30)
            r.raise_for_status()

            pdf_m = PDF_RE.search(r.text)
            if not pdf_m:
                append_manifest(args.manifest, dict(
                    course=course, semester=sem, academic_year=year,
                    paper_code="", paper_name="", paper_url=url, pdf_url="",
                    structured_path="", unstructured_path="", status="NO_PDF_LINK",
                    downloaded_at=""))
                fail += 1
                log(f"[{i}/{total}] NO PDF LINK  {url}")
                continue

            pdf_url = urljoin(BASE, pdf_m.group(1))
            code_m = CODE_RE.search(r.text)
            name_m = NAME_RE.search(r.text)
            code = code_m.group(1) if code_m else "UNKNOWN"
            pname = name_m.group(1) if name_m else slug.replace("-", " ")

            fname = build_filename(course, sem, year, code, slug)
            struct_rel = os.path.join(course, f"Sem-{int(sem):02d}", year, fname)
            struct_path = os.path.join(args.out, "structured", struct_rel)
            flat_path = os.path.join(args.out, "unstructured", fname)

            # 2) download PDF
            time.sleep(args.delay + random.uniform(0, 0.4))
            pr = session.get(pdf_url, timeout=60)
            pr.raise_for_status()
            if not pr.content.startswith(b"%PDF"):
                append_manifest(args.manifest, dict(
                    course=course, semester=sem, academic_year=year,
                    paper_code=code, paper_name=pname, paper_url=url, pdf_url=pdf_url,
                    structured_path="", unstructured_path="", status="NOT_A_PDF",
                    downloaded_at=""))
                fail += 1
                log(f"[{i}/{total}] NOT A PDF  {url}")
                continue

            os.makedirs(os.path.dirname(struct_path), exist_ok=True)
            with open(struct_path, "wb") as fh:
                fh.write(pr.content)

            # 3) flat copy for unstructured folder (collision-safe)
            n = 2
            while os.path.exists(flat_path):
                base, ext = os.path.splitext(fname)
                flat_path = os.path.join(args.out, "unstructured", f"{base}__dup{n}{ext}")
                n += 1
            shutil.copyfile(struct_path, flat_path)

            append_manifest(args.manifest, dict(
                course=course, semester=sem, academic_year=year,
                paper_code=code, paper_name=pname, paper_url=url, pdf_url=pdf_url,
                structured_path=struct_rel, unstructured_path=os.path.basename(flat_path),
                status="OK", downloaded_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")))
            ok += 1
            log(f"[{i}/{total}] OK  {fname}  ({len(pr.content)//1024} KB)")

        except KeyboardInterrupt:
            log("\n[!] paused by user - rerun the same command to resume")
            break
        except Exception as e:
            append_manifest(args.manifest, dict(
                course=course, semester=sem, academic_year=year,
                paper_code="", paper_name="", paper_url=url, pdf_url="",
                structured_path="", unstructured_path="",
                status=f"ERROR: {type(e).__name__}: {e}", downloaded_at=""))
            fail += 1
            log(f"[{i}/{total}] ERROR {url} -> {e}")

    dt = time.time() - t0
    log(f"\n[i] session done in {dt/60:.1f} min: {ok} downloaded, {skip} skipped/resumed, {fail} failed")
    log(f"[i] structured -> {os.path.abspath(os.path.join(args.out, 'structured'))}")
    log(f"[i] unstructured -> {os.path.abspath(os.path.join(args.out, 'unstructured'))}")
    log(f"[i] manifest -> {os.path.abspath(args.manifest)}")


if __name__ == "__main__":
    sys.exit(main())
