```markdown
# IIT Google Scholar Scraper — How to Run

This repo contains:

- **IIT Faculty Google Scholar Links.zip** → three CSV files with faculty names and Google Scholar links:
  - `Computer Science Faculty Google Scholar Links.csv`
  - `Applied Math Faculty Google Scholar Links.csv`
  - `ITM Faculty Google Scholar Links.csv`
- **scholar_department_extract.py** → scrapes paper-level metadata from Google Scholar  
- **make_yearly_notebooklm_docs.py** → converts the scraped CSV into yearly text files for NotebookLM  

All commands below assume that:
- the three CSV files are **in the same folder as your Python scripts**, and  
- you are running the commands from that folder in your terminal.

---

## STEP 1 — Put the CSV files in the working folder

Unzip **IIT Faculty Google Scholar Links.zip** and place the three CSV files **in the same directory as**:

```

scholar_department_extract.py
make_yearly_notebooklm_docs.py

````

(For example, if both scripts are in `Downloads`, put the CSVs there too.)

---

## STEP 2 — Run the **extract script** (3 commands)

### 1️⃣ Computer Science

```powershell
python scholar_department_extract.py `
  --input_csv "Computer Science Faculty Google Scholar Links.csv" `
  --department CS `
  --name_col "Faculty Name" `
  --url_col "Google Scholar Link" `
  --out_csv "cs_publications_2015_2026.csv" `
  --sleep_fetch 12.0
````

### 2️⃣ Applied Math

```powershell
python scholar_department_extract.py `
  --input_csv "Applied Math Faculty Google Scholar Links.csv" `
  --department MATH `
  --name_col "Faculty Name" `
  --url_col "Google Scholar Link" `
  --out_csv "math_publications_2015_2026.csv" `
  --sleep_fetch 12.0
```

### 3️⃣ ITM

```powershell
python scholar_department_extract.py `
  --input_csv "ITM Faculty Google Scholar Links.csv" `
  --department ITM `
  --name_col "Faculty Name" `
  --url_col "Google Scholar Link" `
  --out_csv "itm_publications_2015_2026.csv" `
  --sleep_fetch 12.0
```

If everything works, you should get three files in your working folder:

```
cs_publications_2015_2026.csv
math_publications_2015_2026.csv
itm_publications_2015_2026.csv
```

---

## STEP 3 — Make yearly NotebookLM documents (3 commands)

Create output folders first (from the same directory):

```powershell
mkdir notebooklm\CS
mkdir notebooklm\MATH
mkdir notebooklm\ITM
```

### 4️⃣ CS yearly docs

```powershell
python make_yearly_notebooklm_docs.py `
  --dept CS `
  --input_csv "cs_publications_2015_2026.csv" `
  --out_dir "notebooklm/CS" `
  --git_repo "https://github.com/YOUR_REPO_HERE"
```

### 5️⃣ MATH yearly docs

```powershell
python make_yearly_notebooklm_docs.py `
  --dept MATH `
  --input_csv "math_publications_2015_2026.csv" `
  --out_dir "notebooklm/MATH" `
  --git_repo "https://github.com/YOUR_REPO_HERE"
```

### 6️⃣ ITM yearly docs

```powershell
python make_yearly_notebooklm_docs.py `
  --dept ITM `
  --input_csv "itm_publications_2015_2026.csv" `
  --out_dir "notebooklm/ITM" `
  --git_repo "https://github.com/YOUR_REPO_HERE"
```

This creates files like:

```
notebooklm/CS/CS_2015.txt ... CS_2026.txt
notebooklm/MATH/MATH_2015.txt ... MATH_2026.txt
notebooklm/ITM/ITM_2015.txt ... ITM_2026.txt
```

These are what you upload to NotebookLM.

---

## Optional — Test on **one professor only (Ioan Raicu)**

Ioan’s Scholar user ID: **jE73HYAAAAAJ**

Run (limit to 5 papers so it’s fast):

```powershell
python scholar_department_extract.py `
  --single_user_id jE73HYAAAAAJ `
  --single_name "Ioan Raicu" `
  --department CS `
  --single_out_csv "ioan_raicu_sample.csv" `
  --max_pubs_per_faculty 5 `
  --sleep_fetch 12.0
```

This produces:

```
ioan_raicu_sample.csv
```

---

## IMPORTANT NOTE (status of scraping)

I **was not able to fully finish scraping all departments yet** because Google Scholar kept blocking requests with **rate limits (429) and CAPTCHA pages**, even when I increased delays.

* Increasing sleep time (10s → 20s → 40s) **did not fully remove CAPTCHA blocks**.
* The **scraping logic itself works** (it can read faculty pages, find papers, and extract metadata).
* What remains is improving how we handle Scholar’s anti-bot protection so the script can run reliably at scale.

```
```
