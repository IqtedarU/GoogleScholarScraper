import os
import argparse
import pandas as pd
import math

YEAR_MIN = 2015
YEAR_MAX = 2026

DISCLAIMER_TEMPLATE = """Data source: Google Scholar (scholar.google.com)
Department: {dept}
Year: {year}

Notes:
- Every attempt was made to identify Illinois Institute of Technology (IIT) faculty in {dept} and collect publication metadata from their Google Scholar profiles.
- The document contains publication titles and available descriptions/abstract-like snippets for works published in {year}.
- Author names are intentionally omitted from entries.
- Citation counts are as reported by Google Scholar at collection time. A "citations_per_year_proxy" is computed as:
    cited_by_total / (2026 - publication_year + 1)
- Git repository for the collection code: {git_repo}

------------------------------------------------------------
"""

def clean_text(x):
    if x is None:
        return ""
    if isinstance(x, float) and math.isnan(x):
        return ""
    return str(x).strip()

def ensure_dir(p):
    os.makedirs(p, exist_ok=True)

def write_year_file(df_year, out_path, dept, year, git_repo):
    ensure_dir(os.path.dirname(out_path) or ".")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(DISCLAIMER_TEMPLATE.format(dept=dept, year=year, git_repo=git_repo))

        # Sort: most-cited first (fallback to 0)
        df_year = df_year.copy()
        df_year["cited_by_total_sort"] = pd.to_numeric(df_year.get("cited_by_total", 0), errors="coerce").fillna(0).astype(int)
        df_year = df_year.sort_values(["cited_by_total_sort", "title"], ascending=[False, True])

        for idx, row in df_year.iterrows():
            title = clean_text(row.get("title"))
            abstract = clean_text(row.get("abstract"))
            cited_by_total = clean_text(row.get("cited_by_total"))
            proxy = clean_text(row.get("citations_per_year_proxy"))

            f.write(f"TITLE: {title}\n")
            f.write(f"CITED_BY_TOTAL: {cited_by_total or 'N/A'}\n")
            f.write(f"CITATIONS_PER_YEAR_PROXY: {proxy or 'N/A'}\n")
            f.write("ABSTRACT_OR_DESCRIPTION:\n")
            f.write((abstract if abstract else "N/A") + "\n")
            f.write("\n" + "-"*60 + "\n\n")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dept", required=True, help="CS / MATH / ITM (label used in headers and filenames)")
    ap.add_argument("--input_csv", required=True, help="Department publications CSV (one row per paper)")
    ap.add_argument("--out_dir", required=True, help="Folder to write yearly .txt files")
    ap.add_argument("--git_repo", default="(ADD_GIT_REPO_URL_HERE)", help="Git repo URL to include in file headers")
    ap.add_argument("--year_min", type=int, default=YEAR_MIN)
    ap.add_argument("--year_max", type=int, default=YEAR_MAX)
    args = ap.parse_args()

    df = pd.read_csv(args.input_csv)

    # Expect at least: title, publication_year, cited_by_total, citations_per_year_proxy, abstract
    if "publication_year" not in df.columns:
        raise ValueError("Input CSV must contain 'publication_year' column.")

    df["publication_year"] = pd.to_numeric(df["publication_year"], errors="coerce")

    for y in range(args.year_min, args.year_max + 1):
        df_year = df[df["publication_year"] == y]
        out_path = os.path.join(args.out_dir, f"{args.dept}_{y}.txt")
        write_year_file(df_year, out_path, args.dept, y, args.git_repo)
        print(f"Wrote {len(df_year)} entries -> {out_path}")

if __name__ == "__main__":
    main()
