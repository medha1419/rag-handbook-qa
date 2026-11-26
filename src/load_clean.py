"""
load_clean.py — Load the employee handbook PDF and clean it for chunking.

Output: a list of page records
    {"page": int, "text": str}
saved to data/pages.json, so chunking can keep page numbers for citations.

Usage:
    python src/load_clean.py data/handbook.pdf --inspect   # look before you clean
    python src/load_clean.py data/handbook.pdf             # clean and save
"""
import argparse
import json
import re
from collections import Counter

import pymupdf  # pip install pymupdf


# ---------- 1. Load ----------
def load_pages(pdf_path):
    """Return a list of (page_number, raw_text). Page numbers start at 1."""
    doc = pymupdf.open(pdf_path)
    # sort=True reads blocks top-to-bottom, left-to-right (helps 2-column layouts)
    return [(i + 1, page.get_text("text", sort=True)) for i, page in enumerate(doc)]


# ---------- 2. Find repeated headers/footers ----------
def find_repeated_lines(pages, edge_lines=3, min_ratio=0.5):
    """
    A line that appears in the top/bottom `edge_lines` of at least `min_ratio`
    of all pages is a header or footer (e.g. "BOLD Employee Handbook | Confidential").
    Digits are masked so "Page 3" and "Page 4" count as the same line.
    """
    counter = Counter()
    for _, text in pages:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        edges = lines[:edge_lines] + lines[-edge_lines:]
        counter.update({re.sub(r"\d+", "#", l) for l in edges})
    threshold = max(2, int(len(pages) * min_ratio))
    return {line for line, n in counter.items() if n >= threshold}


# ---------- 3. Clean one page ----------
PAGE_NUM = re.compile(r"^\s*(page\s*)?\d+(\s*(of|/)\s*\d+)?\s*$", re.I)
TOC_LINE = re.compile(r"\.{4,}\s*\d+\s*$")          # "Leave Policy ........ 12"
BULLET = re.compile(r"^\s*[•●▪◦■·\-–]\s*")


def clean_page(text, repeated):
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            out.append("")                            # keep blank = paragraph break
            continue
        if re.sub(r"\d+", "#", s) in repeated:        # header / footer
            continue
        if PAGE_NUM.match(s):                         # bare page number
            continue
        s = BULLET.sub("- ", s)                       # normalise bullets
        out.append(s)

    text = "\n".join(out)
    text = text.replace("­", "")                 # soft hyphens
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)      # re-join hyphenated words
    # Join lines broken mid-sentence: a line not ending in . : ; ? ! and the next
    # line starting lowercase belong to the same sentence.
    text = re.sub(r"(?<![.:;?!])\n(?=[a-z0-9(])", " ", text)
    text = re.sub(r"[ \t]+", " ", text)               # collapse spaces
    text = re.sub(r"\n{3,}", "\n\n", text)            # collapse blank lines
    return text.strip()


def is_toc_page(text):
    """A page where most lines look like 'Title ..... 12' is a table of contents."""
    lines = [l for l in text.splitlines() if l.strip()]
    return bool(lines) and sum(bool(TOC_LINE.search(l)) for l in lines) / len(lines) > 0.4


# ---------- 4. Pipeline ----------
def load_and_clean(pdf_path):
    pages = load_pages(pdf_path)
    repeated = find_repeated_lines(pages)
    records = []
    for num, raw in pages:
        if is_toc_page(raw):
            continue
        text = clean_page(raw, repeated)
        if len(text) > 50:                            # drop near-empty pages (covers, dividers)
            records.append({"page": num, "text": text})
    return records, repeated


def inspect(pdf_path, n=3):
    """Print raw text of the first n pages and the detected headers/footers."""
    pages = load_pages(pdf_path)
    print(f"{len(pages)} pages\n")
    for num, raw in pages[:n]:
        print(f"===== RAW PAGE {num} =====\n{raw[:1500]}\n")
    print("Detected repeated header/footer lines:", find_repeated_lines(pages))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--out", default="data/pages.json")
    ap.add_argument("--inspect", action="store_true")
    args = ap.parse_args()

    if args.inspect:
        inspect(args.pdf)
    else:
        records, repeated = load_and_clean(args.pdf)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
        chars = sum(len(r["text"]) for r in records)
        print(f"Kept {len(records)} pages, {chars:,} chars. Removed headers/footers: {repeated}")
