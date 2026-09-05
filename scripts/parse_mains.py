"""
Stage 2 of the PYQ pipeline: UPSC mains GS papers (PDF) -> structured rows.

Deterministic. No model calls, no network. Produces an intermediate JSON file
that stage 2 (tag_pyq.py) turns into importer-ready rows.

Usage
-----
    python parse_mains.py data/pdfs/*.pdf -o data/pyq/_raw_mains.json
    python parse_mains.py data/pdfs/mains_2019_gs2.pdf --inspect   # eyeball first
    python parse_mains.py extracted/2019_gs2.txt -o out.json       # .txt also works

Filename convention (anything containing a 4-digit year and gs<N>):
    mains_2019_gs2.pdf, 2019-GS-II.pdf, cse2019_gs2.pdf  -> year=2019, gs=2
Override with --year / --gs when the filename is uninformative.

Requires poppler-utils (`pdftotext`); falls back to pdfplumber if absent.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass

# --- patterns ---------------------------------------------------------------

# "1." / "1)" / "Q1." / "Q.1" at the start of a line, followed by real text.
Q_START = re.compile(r"^\s*(?:Q\.?\s*)?(\d{1,2})\s*[.)]\s+(?=\S)")

# "(Answer in 150 words) 10" / "(150 words) 10" / "(Answer in 250 words)  20"
TRAILER = re.compile(r"\(\s*(?:Answer\s+in\s+)?(\d{2,3})\s*words?\s*\)\s*(\d{1,3})\b")

SECTION = re.compile(r"^\s*SECTION\s*[-–—]?\s*['\"]?\s*([AB])\s*['\"]?\s*$", re.I)

DEVANAGARI = re.compile(r"[ऀ-ॿ]")

# page furniture: bare page numbers, ": 3 :", dotted rules, "P.T.O."
NOISE = re.compile(
    r"^\s*(?:[:\-–—.\s]*\d{1,3}[:\-–—.\s]*|P\.?\s*T\.?\s*O\.?|\.{3,}|[-–—_]{3,})\s*$",
    re.I,
)

YEAR_IN_NAME = re.compile(r"(19|20)\d{2}")
GS_IN_NAME = re.compile(r"g\.?s\.?[\s_\-]*(iv|iii|ii|i|[1-4])\b", re.I)
ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4}

MARKS_PER_PAPER = 250  # every mains GS paper totals 250


@dataclass
class Row:
    year: int
    paper: str          # always "mains" here — matches the importer's field
    gs_paper: int       # 1-4, kept for the tagger's context, dropped before import
    section: str | None
    q_no: int
    question: str
    word_limit: int | None
    marks: int | None
    source_file: str


# --- text extraction --------------------------------------------------------

def extract_text(path: str) -> str:
    if path.lower().endswith(".txt"):
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()

    if shutil.which("pdftotext"):
        out = subprocess.run(
            ["pdftotext", "-layout", "-enc", "UTF-8", path, "-"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout

    try:
        import pdfplumber
    except ImportError:
        sys.exit(
            "Neither pdftotext nor pdfplumber available.\n"
            "  sudo apt install poppler-utils      (preferred)\n"
            "  uv pip install pdfplumber           (fallback)"
        )
    with pdfplumber.open(path) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def clean_lines(text: str) -> list[str]:
    """Drop Hindi translations and page furniture, keep everything else."""
    kept = []
    for raw in text.splitlines():
        line = raw.replace("\xa0", " ").rstrip()
        if not line.strip():
            kept.append("")
            continue
        if NOISE.match(line):
            continue
        letters = [c for c in line if c.isalpha()]
        if letters and len(DEVANAGARI.findall(line)) / len(letters) > 0.2:
            continue  # bilingual paper: this is the Hindi rendering
        kept.append(line)
    return kept


# --- parsing ----------------------------------------------------------------

def parse_paper(text: str, year: int, gs: int, source_file: str) -> list[Row]:
    lines = clean_lines(text)

    section: str | None = None
    just_saw_section = False
    blocks: list[dict] = []
    current: dict | None = None

    for line in lines:
        m_sec = SECTION.match(line)
        if m_sec:
            section = m_sec.group(1).upper()
            just_saw_section = True
            continue

        m_q = Q_START.match(line)
        if m_q:
            n = int(m_q.group(1))
            last = blocks[-1]["q_no"] if blocks else 0
            # Accept as a new question only if it continues the sequence, or
            # restarts at 1 right after a section header. Otherwise it's an
            # enumerated item *inside* a question and must not split it.
            if n == last + 1 or (n == 1 and just_saw_section):
                current = {
                    "q_no": n,
                    "section": section,
                    "parts": [line[m_q.end():]],
                }
                blocks.append(current)
                just_saw_section = False
                continue

        if current is not None:
            current["parts"].append(line)

    rows: list[Row] = []
    for b in blocks:
        body = " ".join(p.strip() for p in b["parts"] if p.strip())
        body = re.sub(r"\s{2,}", " ", body).strip()

        word_limit = marks = None
        m_t = TRAILER.search(body)
        if m_t:
            word_limit, marks = int(m_t.group(1)), int(m_t.group(2))
            body = (body[: m_t.start()] + " " + body[m_t.end():]).strip()

        body = re.sub(r"\s{2,}", " ", body).strip()
        if not body:
            continue

        rows.append(Row(
            year=year, paper="mains", gs_paper=gs, section=b["section"],
            q_no=b["q_no"], question=body, word_limit=word_limit,
            marks=marks, source_file=os.path.basename(source_file),
        ))
    return rows


def meta_from_name(path: str) -> tuple[int | None, int | None]:
    name = os.path.basename(path)
    y = YEAR_IN_NAME.search(name)
    g = GS_IN_NAME.search(name)
    gs = None
    if g:
        tok = g.group(1).lower()
        gs = ROMAN.get(tok, None) or (int(tok) if tok.isdigit() else None)
    return (int(y.group(0)) if y else None, gs)


def validate(rows: list[Row], label: str) -> list[str]:
    """Checksums that catch a mangled parse instead of letting it through."""
    problems = []
    if not rows:
        return [f"{label}: no questions parsed at all"]

    total = sum(r.marks for r in rows if r.marks)
    if total != MARKS_PER_PAPER:
        problems.append(f"{label}: marks total {total}, expected {MARKS_PER_PAPER}")

    missing = [r.q_no for r in rows if r.marks is None]
    if missing:
        problems.append(f"{label}: no marks trailer found for Q{missing}")

    # Numbering runs 1..N within a section; Section B legitimately restarts at 1.
    by_section: dict[str | None, list[int]] = {}
    for r in rows:
        by_section.setdefault(r.section, []).append(r.q_no)
    for sec, nums in by_section.items():
        if nums != list(range(1, len(nums) + 1)):
            problems.append(f"{label} section {sec or '-'}: gap or repeat in numbering -> {nums}")

    short = [r.q_no for r in rows if len(r.question) < 40]
    if short:
        problems.append(f"{label}: suspiciously short text for Q{short}")

    return problems


# --- cli --------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="PDF (or pre-extracted .txt) papers")
    ap.add_argument("-o", "--out", help="write JSON here")
    ap.add_argument("--year", type=int, help="override year for all inputs")
    ap.add_argument("--gs", type=int, choices=[1, 2, 3, 4], help="override GS paper")
    ap.add_argument("--inspect", action="store_true",
                    help="print parsed questions to stdout instead of writing JSON")
    args = ap.parse_args()

    all_rows: list[Row] = []
    all_problems: list[str] = []

    for path in args.files:
        year, gs = meta_from_name(path)
        year, gs = args.year or year, args.gs or gs
        if year is None or gs is None:
            all_problems.append(f"{path}: can't infer year/GS from filename — pass --year/--gs")
            continue

        rows = parse_paper(extract_text(path), year, gs, path)
        label = f"{year} GS{gs}"
        all_problems += validate(rows, label)
        all_rows += rows

        if args.inspect:
            print(f"\n=== {label}  ({len(rows)} questions) ===")
            for r in rows:
                head = r.question if len(r.question) <= 110 else r.question[:107] + "..."
                print(f"  [{r.section or '-'}] Q{r.q_no:>2}  {r.marks or '?':>3}m "
                      f"{r.word_limit or '?':>4}w  {head}")

    if all_problems:
        print("\n--- CHECK THESE ---", file=sys.stderr)
        for p in all_problems:
            print("  ! " + p, file=sys.stderr)

    print(f"\nparsed {len(all_rows)} questions from {len(args.files)} file(s)",
          file=sys.stderr)

    if args.out and not args.inspect:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump([asdict(r) for r in all_rows], fh, ensure_ascii=False, indent=2)
        print(f"wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
