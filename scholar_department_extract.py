"""
scholar_department_extract.py

Given ONE department CSV with columns:
  - name
  - scholar_url   (can be NaN)

This script:
  1) Visits each Google Scholar author profile (via scholarly)
  2) Enumerates publications
  3) For each publication, opens the `view_citation` page
  4) Extracts:
      - faculty_name
      - publication year
      - title
      - "Description" (often abstract-like; may be missing)
      - total citations (Cited by N)
      - citations per year for 2015..2026 if the bar chart is present
  5) Writes ONE department-wide CSV.

It also includes a "single professor" mode that prints/exports Ioan Raicu (or any user=ID).

Notes:
- Google Scholar can rate-limit / CAPTCHA. Use --sleep and caching.
- Abstracts are not guaranteed; Scholar "Description" is often missing.
"""

import os
import re
import time
import math
import argparse
from typing import Optional, Dict, Any, List, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup

YEAR_MIN = 2015
YEAR_MAX = 2026

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}

BASE = "https://scholar.google.com"


def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^a-z0-9_]+", "", s)
    return s[:120] or "x"


def scholar_author_id_from_url(url: str) -> Optional[str]:
    if not url or not isinstance(url, str):
        return None
    m = re.search(r"[?&]user=([^&]+)", url)
    return m.group(1) if m else None


def cache_get(url: str, cache_path: str, sleep_s: float = 0.0, force: bool = False) -> str:
    if (not force) and os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    if sleep_s > 0:
        time.sleep(sleep_s)

    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    html = r.text

    ensure_dir(os.path.dirname(cache_path))
    with open(cache_path, "w", encoding="utf-8", errors="ignore") as f:
        f.write(html)
    return html


def looks_like_captcha(html: str) -> bool:
    # best-effort CAPTCHA detection
    h = html.lower()
    return ("recaptcha" in h) or ("unusual traffic" in h) or ("sorry" in h and "automated queries" in h)


def parse_author_page_for_pubs(html: str) -> List[Dict[str, Any]]:
    """
    Parses an author profile page and returns publication rows with:
      - title
      - year (if present)
      - cited_by (if present)
      - view_citation_url (exact link from Scholar)
    """
    soup = BeautifulSoup(html, "html.parser")
    pubs = []

    # Each pub row is a <tr class="gsc_a_tr">
    for tr in soup.select("tr.gsc_a_tr"):
        a = tr.select_one("a.gsc_a_at")
        if not a:
            continue
        title = a.get_text(strip=True)
        href = a.get("href")  # includes citation_for_view
        view_url = BASE + href if href and href.startswith("/") else href

        year = None
        y = tr.select_one("span.gsc_a_h")
        if y:
            try:
                year = int(y.get_text(strip=True))
            except Exception:
                year = None

        cited_by = None
        cb = tr.select_one("a.gsc_a_ac")
        if cb:
            txt = cb.get_text(strip=True)
            if txt.isdigit():
                cited_by = int(txt)

        pubs.append({
            "title": title,
            "year": year,
            "cited_by_from_list": cited_by,
            "view_citation_url": view_url
        })

    return pubs


def next_cstart_from_author_page(html: str) -> Optional[int]:
    """
    Author pages paginate via 'cstart' and 'pagesize'.
    We'll look for the "Next" button.
    """
    soup = BeautifulSoup(html, "html.parser")
    btn = soup.select_one("button#gsc_bpf_next")
    if not btn:
        return None
    disabled = btn.has_attr("disabled")
    if disabled:
        return None
    # We can’t directly read next cstart from the button; we track cstart ourselves.
    return 1  # sentinel meaning "has next"


def get_all_author_pubs(user_id: str, cache_dir: str, sleep_fetch: float = 2.0,
                        pagesize: int = 100, max_pubs: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Paginates the author profile and returns all pubs.
    """
    pubs_all = []
    cstart = 0
    page = 0

    while True:
        url = f"{BASE}/citations?hl=en&user={user_id}&cstart={cstart}&pagesize={pagesize}"
        cache_path = os.path.join(cache_dir, "author_pages", user_id, f"cstart_{cstart}.html")
        html = cache_get(url, cache_path=cache_path, sleep_s=sleep_fetch, force=False)

        if looks_like_captcha(html):
            raise RuntimeError("CAPTCHA / unusual traffic page detected. Increase sleep or try later.")

        pubs = parse_author_page_for_pubs(html)
        if not pubs:
            break

        pubs_all.extend(pubs)

        if max_pubs is not None and len(pubs_all) >= max_pubs:
            pubs_all = pubs_all[:max_pubs]
            break

        has_next = next_cstart_from_author_page(html)
        if not has_next:
            break

        cstart += pagesize
        page += 1
        if page > 500:  # safety
            break

    return pubs_all


def parse_view_citation(html: str) -> Dict[str, Any]:
    """
    Parse the view_citation page for:
      - title
      - Publication date -> pub_year
      - Description -> abstract-ish
      - Total citations -> cited_by_total
      - citations per year graph -> cites_by_year (best-effort)
    """
    soup = BeautifulSoup(html, "html.parser")

    title = None
    t = soup.select_one("#gsc_oci_title")
    if t:
        title = t.get_text(strip=True)
    else:
        t2 = soup.select_one(".gsc_oci_title_link")
        if t2:
            title = t2.get_text(strip=True)

    # Fields
    fields = {}
    for f, v in zip(soup.select(".gsc_oci_field"), soup.select(".gsc_oci_value")):
        fields[f.get_text(strip=True)] = v.get_text(" ", strip=True)

    abstract = fields.get("Description")

    pub_year = None
    pub_date = fields.get("Publication date")
    if pub_date:
        m = re.search(r"(\d{4})", pub_date)
        if m:
            pub_year = int(m.group(1))

    # Total citations: prefer parsing from the field "Total citations"
    cited_by_total = None
    if "Total citations" in fields:
        # often looks like "Cited by 5179"
        m = re.search(r"Cited by\s+(\d+)", fields["Total citations"])
        if m:
            cited_by_total = int(m.group(1))
    if cited_by_total is None:
        # fallback: search anywhere
        m = re.search(r"Cited by\s+(\d+)", html)
        if m:
            cited_by_total = int(m.group(1))

    # Citations-per-year bars: best-effort regex for embedded pairs/arrays
    cites_by_year: Dict[int, int] = {}

    # Pattern A: [[2011,23],[2012,45],...]
    m = re.search(
        r"(\[\s*\[\s*\d{4}\s*,\s*\d+\s*\]\s*(?:,\s*\[\s*\d{4}\s*,\s*\d+\s*\]\s*)+\])",
        html
    )
    if m:
        blob = m.group(1)
        pairs = re.findall(r"\[\s*(\d{4})\s*,\s*(\d+)\s*\]", blob)
        for y, c in pairs:
            cites_by_year[int(y)] = int(c)
    else:
        # Pattern B: years=[...], cites=[...]
        m2 = re.search(
            r"years\s*=\s*(\[\s*\d{4}(?:\s*,\s*\d{4})+\s*\]).*?"
            r"cites\s*=\s*(\[\s*\d+(?:\s*,\s*\d+)+\s*\])",
            html,
            flags=re.DOTALL
        )
        if m2:
            years_blob, cites_blob = m2.group(1), m2.group(2)
            years = [int(x) for x in re.findall(r"\d{4}", years_blob)]
            cites = [int(x) for x in re.findall(r"\d+", cites_blob)]
            for y, c in zip(years, cites):
                cites_by_year[y] = c

    return {
        "title": title,
        "pub_year": pub_year,
        "cited_by_total": cited_by_total,
        "abstract": abstract,
        "cites_by_year": cites_by_year,
        "fields": fields
    }


def cites_2015_2026(cites_by_year: Dict[int, int]) -> Dict[str, Optional[int]]:
    out = {}
    for y in range(YEAR_MIN, YEAR_MAX + 1):
        out[f"cites_{y}"] = cites_by_year.get(y)
    return out

from playwright.sync_api import sync_playwright
import re

def extract_cites_by_year_playwright(view_citation_url: str, timeout_ms: int = 30000) -> dict[int, int]:
    """
    Opens a Scholar view_citation page in a headless browser and extracts the
    citations-per-year bars (when present).
    Returns: {year: cites}
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(view_citation_url, wait_until="networkidle", timeout=timeout_ms)

        # If you get blocked, Scholar may show "unusual traffic"
        body = page.content().lower()
        if "unusual traffic" in body or "automated queries" in body or "recaptcha" in body:
            browser.close()
            raise RuntimeError("Blocked by Google Scholar (CAPTCHA/unusual traffic). Increase sleep or try later.")

        cites = {}

        # Scholar graphs often have clickable bars with aria-label or tooltip-ish text.
        # We try multiple approaches to be robust.

        # Approach A: read all aria-labels on graph elements
        aria_nodes = page.locator("[aria-label*='citations']").all()
        for n in aria_nodes:
            txt = (n.get_attribute("aria-label") or "").lower()
            # common patterns: "2018: 25 citations" etc
            m = re.search(r"(\d{4}).*?(\d+)\s+cit", txt)
            if m:
                y, c = int(m.group(1)), int(m.group(2))
                cites[y] = c

        # Approach B: scan visible text around the graph for "YYYY" and counts (fallback)
        if not cites:
            graph_text = page.locator("body").inner_text()
            # very loose fallback; you can tighten after you see actual strings
            for m in re.finditer(r"(\d{4})\s+(\d+)\s+cit", graph_text.lower()):
                y, c = int(m.group(1)), int(m.group(2))
                cites[y] = c

        browser.close()
        return cites


def citations_per_year_proxy(total_cites: Optional[int], pub_year: Optional[int], now_year: int = YEAR_MAX) -> Optional[float]:
    if total_cites is None or pub_year is None:
        return None
    denom = (now_year - pub_year + 1)
    if denom <= 0:
        denom = 1
    return float(total_cites) / float(denom)


def process_one_professor(user_id: str, faculty_name: str, department: str,
                          cache_dir: str, sleep_fetch: float,
                          max_pubs: Optional[int] = None) -> pd.DataFrame:
    pubs = get_all_author_pubs(
        user_id=user_id,
        cache_dir=cache_dir,
        sleep_fetch=sleep_fetch,
        pagesize=100,
        max_pubs=max_pubs
    )

    rows = []
    for i, p in enumerate(pubs):
        view_url = p["view_citation_url"]
        year_from_list = p.get("year")
        cited_from_list = p.get("cited_by_from_list")

        cache_path = os.path.join(cache_dir, "view_pages", user_id, f"pub_{i:05d}.html")
        html = cache_get(view_url, cache_path=cache_path, sleep_s=sleep_fetch, force=False)
        cites_by_year = extract_cites_by_year_playwright(view_url)

        if looks_like_captcha(html):
            raise RuntimeError("CAPTCHA / unusual traffic page detected while fetching view_citation pages.")

        parsed = parse_view_citation(html)

        pub_year = parsed.get("pub_year") or year_from_list
        cited_total = parsed.get("cited_by_total")
        if cited_total is None:
            cited_total = cited_from_list  # fallback

        cpy_proxy = citations_per_year_proxy(cited_total, pub_year, now_year=YEAR_MAX)

        row = {
            "department": department,
            "faculty_name": faculty_name,
            "title": parsed.get("title") or p.get("title"),
            "publication_year": pub_year,
            "cited_by_total": cited_total,
            "citations_per_year_proxy": cpy_proxy,
            "abstract": parsed.get("abstract"),
            "scholar_user_id": user_id,
            "view_citation_url": view_url,
        }
        cites_src = cites_by_year if cites_by_year else (parsed.get("cites_by_year") or {})
        row.update(cites_2015_2026(cites_src))
        rows.append(row)

    df = pd.DataFrame(rows)
    df = df[(df["publication_year"].isna()) | ((df["publication_year"] >= YEAR_MIN) & (df["publication_year"] <= YEAR_MAX))]
    return df


def process_department_csv(input_csv: str, department: str, out_csv: str,
                           name_col: str, url_col: str,
                           cache_dir: str, sleep_fetch: float,
                           max_faculty: Optional[int] = None,
                           max_pubs_per_faculty: Optional[int] = None) -> None:
    df = pd.read_csv(input_csv)

    if name_col not in df.columns or url_col not in df.columns:
        raise ValueError(f"CSV must contain columns '{name_col}' and '{url_col}'. Found: {list(df.columns)}")

    all_frames = []
    n = 0
    for _, r in df.iterrows():
        if max_faculty is not None and n >= max_faculty:
            break

        faculty_name = str(r[name_col]).strip()
        scholar_url = r[url_col]

        if faculty_name == "":
            continue
        if isinstance(scholar_url, float) and math.isnan(scholar_url):
            continue
        if not isinstance(scholar_url, str) or scholar_url.strip() == "":
            continue

        user_id = scholar_author_id_from_url(scholar_url)
        if not user_id:
            continue

        print(f"[{department}] {faculty_name} -> user={user_id}")
        df_prof = process_one_professor(
            user_id=user_id,
            faculty_name=faculty_name,
            department=department,
            cache_dir=cache_dir,
            sleep_fetch=sleep_fetch,
            max_pubs=max_pubs_per_faculty
        )
        all_frames.append(df_prof)
        n += 1

    out = pd.concat(all_frames, ignore_index=True) if all_frames else pd.DataFrame()
    ensure_dir(os.path.dirname(out_csv) or ".")
    out.to_csv(out_csv, index=False)
    print(f"Wrote {len(out)} rows -> {out_csv}")


def main():
    ap = argparse.ArgumentParser()

    ap.add_argument("--input_csv", default=None)
    ap.add_argument("--department", default="CS")
    ap.add_argument("--out_csv", default="dept_publications_2015_2026.csv")
    ap.add_argument("--name_col", default="Faculty Name")
    ap.add_argument("--url_col", default="Google Scholar Link")
    ap.add_argument("--cache_dir", default="cache_scholar")
    ap.add_argument("--sleep_fetch", type=float, default=3.0)
    ap.add_argument("--max_faculty", type=int, default=None)
    ap.add_argument("--max_pubs_per_faculty", type=int, default=None)

    ap.add_argument("--single_user_id", default=None)
    ap.add_argument("--single_name", default="Ioan Raicu")
    ap.add_argument("--single_out_csv", default="single_professor.csv")

    args = ap.parse_args()

    ensure_dir(args.cache_dir)

    if args.single_user_id:
        df_prof = process_one_professor(
            user_id=args.single_user_id,
            faculty_name=args.single_name,
            department=args.department,
            cache_dir=args.cache_dir,
            sleep_fetch=args.sleep_fetch,
            max_pubs=args.max_pubs_per_faculty
        )
        df_prof.to_csv(args.single_out_csv, index=False)
        print(f"Wrote {len(df_prof)} rows -> {args.single_out_csv}")
        print(df_prof.head(10).to_string(index=False))
        return

    if not args.input_csv:
        raise ValueError("Provide --input_csv for department mode OR --single_user_id for single-professor mode.")

    process_department_csv(
        input_csv=args.input_csv,
        department=args.department,
        out_csv=args.out_csv,
        name_col=args.name_col,
        url_col=args.url_col,
        cache_dir=args.cache_dir,
        sleep_fetch=args.sleep_fetch,
        max_faculty=args.max_faculty,
        max_pubs_per_faculty=args.max_pubs_per_faculty
    )


if __name__ == "__main__":
    main()

