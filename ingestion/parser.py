"""
ingestion/parser.py

Responsible for:
- Loading resume data from Kaggle CSV
- Loading resume data from PDF files
- Cleaning and normalizing resume text
- Validating each resume record
- Returning a unified list of structured resume dictionaries

Output format (same for both CSV and PDF):
{
    "id":          "resume_0001",
    "category":    "Data Science",      # from CSV column / PDF folder name
    "resume_text": "cleaned text...",
    "source":      "csv" or "pdf"
}
"""

import re
import fitz                          # PyMuPDF — for PDF parsing
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

from ingestion.metadata_extractor import extract_resume_metadata

load_dotenv()


# ─────────────────────────────────────────
# Constants
# ─────────────────────────────────────────

REQUIRED_COLUMNS = ["Resume_str", "Category"]
MIN_RESUME_LENGTH = 100              # minimum characters to be a valid resume


# ─────────────────────────────────────────
# Text Cleaning  (shared by CSV + PDF)
# ─────────────────────────────────────────

def clean_text(text: str) -> str:
    """
    Cleans raw resume text:
    - Removes HTML tags
    - Removes URLs
    - Removes special characters (keeps basic punctuation)
    - Collapses multiple spaces/newlines into one space
    """
    if not isinstance(text, str):
        return ""

    text = re.sub(r"<[^>]+>", " ", text)                  # remove HTML tags
    text = re.sub(r"http\S+|www\.\S+", " ", text)          # remove URLs
    text = re.sub(r"[^\w\s\.\,\-\(\)\/\+\#]", " ", text)  # remove special chars
    text = re.sub(r"\s+", " ", text)                       # collapse whitespace
    return text.strip()


# ─────────────────────────────────────────
# Validation  (shared by CSV + PDF)
# ─────────────────────────────────────────

def is_valid_resume(resume_text: str, category: str) -> bool:
    """
    Returns True only if:
    - resume_text is non-empty and long enough
    - category is non-empty
    """
    if not resume_text or not category:
        return False
    if len(resume_text.strip()) < MIN_RESUME_LENGTH:
        return False
    return True


# ─────────────────────────────────────────
# CSV Parser
# ─────────────────────────────────────────

def load_resumes_from_csv(csv_path: str) -> list[dict]:
    """
    Loads and parses resumes from the Kaggle CSV file.

    Args:
        csv_path: Path to CSV, e.g. "data/raw/Resume.csv"

    Returns:
        List of resume dicts with keys: id, category, resume_text, source
    """
    path = Path(csv_path)

    if not path.exists():
        raise FileNotFoundError(
            f"CSV file not found: {csv_path}\n"
            f"Please download the Kaggle dataset and place it in data/raw/"
        )

    print(f"\n[CSV] Loading from: {csv_path}")
    df = pd.read_csv(csv_path)

    # Check required columns exist
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"CSV missing required columns: {missing}\n"
            f"Found columns: {list(df.columns)}"
        )

    print(f"[CSV] Total rows found: {len(df)}")

    resumes = []
    skipped = 0

    for index, row in df.iterrows():
        cleaned_text = clean_text(str(row.get("Resume_str", "")))
        category     = str(row.get("Category", "")).strip()

        if not is_valid_resume(cleaned_text, category):
            skipped += 1
            continue

        resumes.append({
            "id":          f"resume_csv_{str(index).zfill(4)}",
            "category":    category,
            "resume_text": cleaned_text,
            "source":      "csv",
            **extract_resume_metadata(cleaned_text, category),
        })

    print(f"[CSV] Parsed:  {len(resumes)} resumes")
    print(f"[CSV] Skipped: {skipped} resumes (too short or missing fields)")
    return resumes


# ─────────────────────────────────────────
# PDF Parser
# ─────────────────────────────────────────

def extract_text_from_pdf(pdf_path: Path) -> str:
    """
    Extracts plain text from a single PDF file using PyMuPDF.

    Args:
        pdf_path: Path object pointing to a .pdf file

    Returns:
        Cleaned text string extracted from the PDF
    """
    try:
        doc = fitz.open(str(pdf_path))
        full_text = ""

        for page in doc:
            full_text += page.get_text()   # extract text page by page

        doc.close()
        return clean_text(full_text)

    except Exception as e:
        print(f"  [WARNING] Could not read PDF: {pdf_path.name} — {e}")
        return ""


def load_resumes_from_pdf_folder(pdf_folder: str) -> list[dict]:
    """
    Loads all PDF resumes from a folder.

    How category is determined:
    - If PDFs are inside sub-folders:  data/raw/pdfs/DataScience/resume1.pdf
      -> category = sub-folder name ("DataScience")
    - If PDFs are all in one flat folder: data/raw/pdfs/resume1.pdf
      -> category = "Unknown"

    Args:
        pdf_folder: Path to folder containing PDF resumes

    Returns:
        List of resume dicts with keys: id, category, resume_text, source
    """
    folder = Path(pdf_folder)

    if not folder.exists():
        raise FileNotFoundError(
            f"PDF folder not found: {pdf_folder}\n"
            f"Please place your PDF files in that folder."
        )

    # Find all PDFs recursively (including sub-folders)
    pdf_files = list(folder.rglob("*.pdf"))

    if not pdf_files:
        print(f"[PDF] No PDF files found in: {pdf_folder}")
        return []

    print(f"\n[PDF] Found {len(pdf_files)} PDF files in: {pdf_folder}")

    resumes = []
    skipped = 0

    for index, pdf_path in enumerate(pdf_files):

        # Determine category from sub-folder name if present
        # e.g. data/raw/pdfs/DataScience/resume.pdf -> "DataScience"
        # e.g. data/raw/pdfs/resume.pdf              -> "Unknown"
        if pdf_path.parent != folder:
            category = pdf_path.parent.name
        else:
            category = "Unknown"

        text = extract_text_from_pdf(pdf_path)

        if not is_valid_resume(text, category):
            print(f"  [SKIP] {pdf_path.name} — too short or empty")
            skipped += 1
            continue

        resumes.append({
            "id":          f"resume_pdf_{str(index).zfill(4)}",
            "category":    category,
            "resume_text": text,
            "source":      "pdf",
            **extract_resume_metadata(text, category),
        })

    print(f"[PDF] Parsed:  {len(resumes)} resumes")
    print(f"[PDF] Skipped: {skipped} resumes (too short or unreadable)")
    return resumes


# ─────────────────────────────────────────
# Unified Loader  (use this everywhere else)
# ─────────────────────────────────────────

def load_all_resumes(
    csv_path: str   = "data/raw/Resume.csv",
    pdf_folder: str = "data/raw/pdfs",
) -> list[dict]:
    """
    Master function — loads from BOTH CSV and PDF,
    returns one unified list in the same format.

    Args:
        csv_path:   Path to Kaggle CSV file
        pdf_folder: Path to folder containing PDF resumes

    Returns:
        Combined list of all resume dicts
    """
    all_resumes = []

    # ── Load CSV ───────────────────────────
    try:
        csv_resumes = load_resumes_from_csv(csv_path)
        all_resumes.extend(csv_resumes)
    except FileNotFoundError as e:
        print(f"[WARNING] Skipping CSV — {e}")

    # ── Load PDF ───────────────────────────
    try:
        pdf_resumes = load_resumes_from_pdf_folder(pdf_folder)
        all_resumes.extend(pdf_resumes)
    except FileNotFoundError as e:
        print(f"[WARNING] Skipping PDF folder — {e}")

    # ── Summary ────────────────────────────
    print(f"\n{'='*50}")
    print(f"TOTAL resumes loaded: {len(all_resumes)}")

    csv_count = sum(1 for r in all_resumes if r["source"] == "csv")
    pdf_count = sum(1 for r in all_resumes if r["source"] == "pdf")
    print(f"  From CSV: {csv_count}")
    print(f"  From PDF: {pdf_count}")

    categories = {}
    for r in all_resumes:
        cat = r["category"]
        categories[cat] = categories.get(cat, 0) + 1

    print(f"\nCategory distribution:")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")

    print(f"{'='*50}\n")
    return all_resumes


# ─────────────────────────────────────────
# Quick Test
# Run: python ingestion/parser.py
# ─────────────────────────────────────────

if __name__ == "__main__":

    resumes = load_all_resumes(
        csv_path   = "data/raw/Resume.csv",
        pdf_folder = "data/raw/pdfs",
    )

    if resumes:
        print("── Sample resume ──")
        sample = resumes[0]
        print(f"ID:       {sample['id']}")
        print(f"Source:   {sample['source']}")
        print(f"Category: {sample['category']}")
        print(f"Preview:  {sample['resume_text'][:300]}...")
