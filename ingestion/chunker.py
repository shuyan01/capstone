"""
ingestion/chunker.py

Responsible for:
- Splitting resume text into smaller chunks for embedding
- Using section-aware splitting (Skills, Experience, Education, etc.)
- Falling back to fixed-size splitting if no sections are detected
- Attaching metadata to each chunk (resume id, category, section name)

Output format — each chunk is a dict:
{
    "chunk_id":    "resume_csv_0001_chunk_00",
    "resume_id":   "resume_csv_0001",
    "category":    "Data Science",
    "source":      "csv",
    "section":     "experience",
    "text":        "chunk text here..."
}
"""

import re
from langchain_text_splitters import RecursiveCharacterTextSplitter


# ─────────────────────────────────────────
# Constants
# ─────────────────────────────────────────

# Fallback chunking settings
CHUNK_SIZE    = 500   # max characters per chunk
CHUNK_OVERLAP = 50    # overlap to preserve context across chunks

# Minimum characters a chunk must have to be kept
MIN_CHUNK_LENGTH = 50

# Section keywords we want to detect
# Each tuple is: (regex_pattern, canonical_name)
SECTION_KEYWORDS = [
    (r"experience|work experience|professional experience|employment history", "experience"),
    (r"education|academic background|academic qualification",                  "education"),
    (r"skills|technical skills|core competencies|key skills|areas of expertise","skills"),
    (r"summary|objective|profile|about me|career objective|professional summary","summary"),
    (r"projects|project experience|key projects|notable projects",              "projects"),
    (r"certifications?|certificates?|licenses?|accreditations?",                "certifications"),
    (r"achievements?|accomplishments?|awards?|honors?",                         "achievements"),
    (r"languages?|hobbies|interests|volunteer|activities",                      "other"),
]

# ─────────────────────────────────────────
# Section Detection  (flexible — handles
# both standalone headings and inline ones)
# ─────────────────────────────────────────

def detect_sections(text: str) -> dict[str, str]:
    """
    Splits resume text into named sections.

    Handles two common formats:

    Format 1 — heading on its own line:
        SKILLS
        Python, SQL, Machine Learning

    Format 2 — heading inline with content:
        SKILLS Python, SQL, Machine Learning EXPERIENCE Software Engineer...

    Returns:
        Dict mapping section_name -> section_text.
        Falls back to {"full_text": text} if nothing detected.
    """

    # Build one big pattern that matches any section keyword
    # Accepts formats like: "SKILLS", "Skills:", "SKILLS -", "Skills  "
    all_keywords = "|".join(
        f"(?P<sec_{i}>{pattern})"
        for i, (pattern, _) in enumerate(SECTION_KEYWORDS)
    )

    section_regex = re.compile(
        rf"(?i)(?:^|\s)({all_keywords})\s*[:\-]?\s*",
    )

    matches = list(section_regex.finditer(text))

    # No sections found at all — return full text
    if not matches:
        return {"full_text": text}

    # Map matched group index back to canonical section name
    def get_canonical(match: re.Match) -> str:
        for i, (_, canonical) in enumerate(SECTION_KEYWORDS):
            if match.group(f"sec_{i}"):
                return canonical
        return "other"

    sections: dict[str, str] = {}

    for idx, match in enumerate(matches):
        canonical = get_canonical(match)
        start     = match.end()                                    # text starts after heading
        end       = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        content   = text[start:end].strip()

        if not content:
            continue

        # If same section appears twice (e.g. two "experience" blocks),
        # append content rather than overwrite
        if canonical in sections:
            sections[canonical] += " " + content
        else:
            sections[canonical] = content

    # Nothing useful extracted — return full text
    if not sections:
        return {"full_text": text}

    return sections


# ─────────────────────────────────────────
# Fallback Splitter
# ─────────────────────────────────────────

_fallback_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " ", ""],
)

def split_long_section(text: str) -> list[str]:
    """
    Splits a long section into smaller chunks using LangChain splitter.
    Used when a single section exceeds CHUNK_SIZE characters.
    """
    return _fallback_splitter.split_text(text)


# ─────────────────────────────────────────
# Core Chunker
# ─────────────────────────────────────────

def chunk_resume(resume: dict) -> list[dict]:
    """
    Splits one resume into a list of chunks with metadata.

    Strategy:
    1. Detect sections (Skills, Experience, Education, etc.)
    2. Each section becomes one or more chunks
    3. Long sections get split further with overlap
    4. Every chunk gets full metadata attached

    Args:
        resume: A resume dict from parser.py

    Returns:
        List of chunk dicts
    """
    resume_id = resume["id"]
    category  = resume["category"]
    source    = resume["source"]
    text      = resume["resume_text"]
    education_tags = resume.get("education_tags", [])
    location_tags = resume.get("location_tags", [])
    industry_tags = resume.get("industry_tags", [])
    job_titles = resume.get("job_titles", [])
    degree_subjects = resume.get("degree_subjects", [])
    education_level = resume.get("education_level", "")
    explicit_years = resume.get("explicit_years", 0)

    sections    = detect_sections(text)
    chunks      = []
    chunk_index = 0

    for section_name, section_text in sections.items():

        if not section_text or len(section_text.strip()) < MIN_CHUNK_LENGTH:
            continue

        # Split long sections further
        if len(section_text) > CHUNK_SIZE:
            sub_chunks = split_long_section(section_text)
        else:
            sub_chunks = [section_text]

        for sub_text in sub_chunks:
            if len(sub_text.strip()) < MIN_CHUNK_LENGTH:
                continue

            chunks.append({
                "chunk_id":  f"{resume_id}_chunk_{str(chunk_index).zfill(2)}",
                "resume_id": resume_id,
                "category":  category,
                "source":    source,
                "section":   section_name,
                "education_tags": education_tags,
                "location_tags": location_tags,
                "industry_tags": industry_tags,
                "job_titles": job_titles,
                "degree_subjects": degree_subjects,
                "education_level": education_level,
                "explicit_years": explicit_years,
                "text":      sub_text.strip(),
            })
            chunk_index += 1

    # Fallback: if nothing was extracted, use full text
    if not chunks and len(text.strip()) >= MIN_CHUNK_LENGTH:
        for i, sub_text in enumerate(split_long_section(text)):
            if len(sub_text.strip()) < MIN_CHUNK_LENGTH:
                continue
            chunks.append({
                "chunk_id":  f"{resume_id}_chunk_{str(i).zfill(2)}",
                "resume_id": resume_id,
                "category":  category,
                "source":    source,
                "section":   "full_text",
                "education_tags": education_tags,
                "location_tags": location_tags,
                "industry_tags": industry_tags,
                "job_titles": job_titles,
                "degree_subjects": degree_subjects,
                "education_level": education_level,
                "explicit_years": explicit_years,
                "text":      sub_text.strip(),
            })

    return chunks


def chunk_all_resumes(resumes: list[dict]) -> list[dict]:
    """
    Chunks every resume in the list.

    Args:
        resumes: List of resume dicts from parser.load_all_resumes()

    Returns:
        Flat list of all chunks across all resumes
    """
    all_chunks    = []
    section_counts = {}

    print(f"Chunking {len(resumes)} resumes...")

    for resume in resumes:
        chunks = chunk_resume(resume)
        all_chunks.extend(chunks)

        for chunk in chunks:
            sec = chunk["section"]
            section_counts[sec] = section_counts.get(sec, 0) + 1

    print(f"Total chunks created:      {len(all_chunks)}")
    print(f"Average chunks per resume: {len(all_chunks) / max(len(resumes), 1):.1f}")

    print(f"\nSection distribution:")
    for sec, count in sorted(section_counts.items(), key=lambda x: -x[1]):
        print(f"  {sec}: {count} chunks")

    return all_chunks


# ─────────────────────────────────────────
# Quick Test
# Run: python ingestion/chunker.py
# ─────────────────────────────────────────

if __name__ == "__main__":
    import sys, os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from ingestion.parser import load_all_resumes

    resumes = load_all_resumes(
        csv_path   = "data/raw/Resume.csv",
        pdf_folder = "data/raw/pdfs",
    )

    # Test on first 10 resumes
    sample = resumes[:10]
    print("\n── Chunking 10 sample resumes ──")
    chunks = chunk_all_resumes(sample)

    print("\n── Sample chunks (first 3) ──")
    for chunk in chunks[:3]:
        print(f"\nChunk ID:  {chunk['chunk_id']}")
        print(f"Section:   {chunk['section']}")
        print(f"Category:  {chunk['category']}")
        print(f"Length:    {len(chunk['text'])} characters")
        print(f"Preview:   {chunk['text'][:200]}...")
