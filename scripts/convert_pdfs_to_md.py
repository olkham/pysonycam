#!/usr/bin/env python3
"""
Convert Sony Camera Remote SDK PDF documentation to Markdown.

Converts all .pdf files in CameraRemoteCommadExamples/ to .md files in docs/sdk/.
Handles the large 600+ page SDK references by splitting into per-page text extraction
and reconstructing structure with headings, tables, and code blocks.

Usage:
    python scripts/convert_pdfs_to_md.py
    python scripts/convert_pdfs_to_md.py --split-pages   # one .md per page (for huge PDFs)
"""

import argparse
import re
import sys
from pathlib import Path

try:
    import pymupdf  # PyMuPDF >= 1.24 uses this import
except ImportError:
    try:
        import fitz as pymupdf  # PyMuPDF < 1.24 fallback
    except ImportError:
        print("PyMuPDF is required. Install it with:")
        print("  pip install pymupdf")
        sys.exit(1)


ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "CameraRemoteCommadExamples"
OUT_DIR = ROOT / "docs" / "sdk"


def sanitize_filename(name: str) -> str:
    """Convert a PDF filename to a clean markdown-safe slug."""
    stem = Path(name).stem
    slug = re.sub(r"[^\w\s-]", "", stem)
    slug = re.sub(r"[\s_]+", "_", slug).strip("-_").lower()
    return slug


def looks_like_heading(line: str) -> bool:
    """Heuristic: short line, title-cased or all-caps, no trailing period."""
    stripped = line.strip()
    if not stripped or len(stripped) > 120:
        return False
    if stripped.endswith((".",":",",")):
        return False
    # Numbered section headings like "1.2.3 Something"
    if re.match(r"^\d+(\.\d+)*\s+\S", stripped):
        return True
    # All-caps headings
    if stripped.isupper() and len(stripped) > 3:
        return True
    return False


def detect_heading_level(line: str) -> int:
    """Guess heading level from numbering pattern."""
    m = re.match(r"^(\d+(?:\.\d+)*)\s", line.strip())
    if m:
        depth = m.group(1).count(".") + 1
        return min(depth, 4)  # cap at h4
    return 2  # default for non-numbered headings


def looks_like_code(line: str) -> bool:
    """Heuristic: lines that look like C/C++ code or hex constants."""
    indicators = [
        r"^\s*(#include|#define|typedef|struct|enum|void|int|unsigned|UINT|BYTE)",
        r"^\s*\{",
        r"^\s*\}",
        r"0x[0-9A-Fa-f]+",
        r"->\s*\w+",
        r"::\w+",
    ]
    return any(re.search(p, line) for p in indicators)


def extract_tables_from_page(page) -> list[dict]:
    """Try to extract tables using PyMuPDF's built-in table finder."""
    tables = []
    try:
        tab_finder = page.find_tables()
        for table in tab_finder:
            rows = table.extract()
            if rows and len(rows) > 1:
                tables.append({
                    "bbox": table.bbox,
                    "rows": rows,
                })
    except Exception:
        pass  # table detection not available or failed
    return tables


def table_to_markdown(rows: list[list]) -> str:
    """Convert a list of rows (list of cells) to a Markdown table."""
    if not rows:
        return ""

    # Clean cells
    clean_rows = []
    for row in rows:
        clean_rows.append([
            (cell or "").replace("\n", " ").replace("|", "\\|").strip()
            for cell in row
        ])

    col_count = max(len(r) for r in clean_rows)
    # Pad rows to same length
    for row in clean_rows:
        while len(row) < col_count:
            row.append("")

    lines = []
    # Header
    lines.append("| " + " | ".join(clean_rows[0]) + " |")
    lines.append("| " + " | ".join(["---"] * col_count) + " |")
    # Body
    for row in clean_rows[1:]:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def process_text_block(text: str) -> str:
    """Process a block of extracted text into Markdown."""
    lines = text.split("\n")
    md_lines = []
    in_code = False
    code_buf = []

    def flush_code():
        nonlocal in_code
        if code_buf:
            md_lines.append("```c")
            md_lines.extend(code_buf)
            md_lines.append("```")
            code_buf.clear()
        in_code = False

    for line in lines:
        stripped = line.strip()

        # Skip page numbers / headers footers that are just numbers
        if re.match(r"^\d{1,4}$", stripped):
            continue
        # Skip common PDF artifacts
        if stripped in ("", "©", "Sony Corporation"):
            if in_code:
                flush_code()
            if stripped == "":
                md_lines.append("")
            continue

        if looks_like_code(line) and not looks_like_heading(line):
            if not in_code:
                in_code = True
            code_buf.append(line.rstrip())
            continue
        else:
            if in_code:
                flush_code()

        if looks_like_heading(stripped):
            level = detect_heading_level(stripped)
            # Remove leading numbering for cleaner headings (keep it in text)
            md_lines.append("")
            md_lines.append(f"{'#' * level} {stripped}")
            md_lines.append("")
        else:
            md_lines.append(stripped)

    if in_code:
        flush_code()

    return "\n".join(md_lines)


def convert_pdf(pdf_path: Path, output_path: Path, split_pages: bool = False):
    """Convert a single PDF to Markdown."""
    print(f"  Opening: {pdf_path.name} ...", flush=True)
    doc = pymupdf.open(str(pdf_path))
    total = len(doc)
    print(f"  Pages: {total}")

    if split_pages:
        # For very large docs, create a directory with one .md per page
        page_dir = output_path.with_suffix("")
        page_dir.mkdir(parents=True, exist_ok=True)

        # Write an index file
        index_lines = [f"# {pdf_path.stem}\n"]
        index_lines.append(f"Converted from `{pdf_path.name}` ({total} pages)\n")
        index_lines.append("## Pages\n")

        for i, page in enumerate(doc):
            page_num = i + 1
            if page_num % 50 == 0 or page_num == 1:
                print(f"    Page {page_num}/{total} ...", flush=True)

            tables = extract_tables_from_page(page)
            text = page.get_text("text")
            md_content = f"# Page {page_num}\n\n"

            if tables:
                # Insert tables at the top, then remaining text
                for tbl in tables:
                    md_content += table_to_markdown(tbl["rows"]) + "\n\n"
                md_content += process_text_block(text)
            else:
                md_content += process_text_block(text)

            page_file = page_dir / f"page_{page_num:04d}.md"
            page_file.write_text(md_content, encoding="utf-8")
            index_lines.append(f"- [Page {page_num}]({page_dir.name}/page_{page_num:04d}.md)")

        index_file = output_path
        index_file.write_text("\n".join(index_lines), encoding="utf-8")
        print(f"  -> {page_dir} ({total} page files + index)")

    else:
        # Single file output
        md_parts = [f"# {pdf_path.stem}\n"]
        md_parts.append(f"*Converted from `{pdf_path.name}` — {total} pages*\n")
        md_parts.append("---\n")

        for i, page in enumerate(doc):
            page_num = i + 1
            if page_num % 50 == 0 or page_num == 1:
                print(f"    Page {page_num}/{total} ...", flush=True)

            tables = extract_tables_from_page(page)
            text = page.get_text("text")

            md_parts.append(f"\n---\n\n<!-- Page {page_num} -->\n")

            if tables:
                for tbl in tables:
                    md_parts.append(table_to_markdown(tbl["rows"]))
                    md_parts.append("")

            md_parts.append(process_text_block(text))

        output_path.write_text("\n".join(md_parts), encoding="utf-8")
        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"  -> {output_path}  ({size_mb:.1f} MB)")

    doc.close()


def main():
    parser = argparse.ArgumentParser(description="Convert SDK PDFs to Markdown")
    parser.add_argument(
        "--split-pages",
        action="store_true",
        help="Split large PDFs into one .md file per page (recommended for 600+ page docs)",
    )
    parser.add_argument(
        "--only",
        type=str,
        help="Only convert PDFs whose filename contains this substring",
    )
    args = parser.parse_args()

    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDF files found in {PDF_DIR}")
        sys.exit(1)

    if args.only:
        pdfs = [p for p in pdfs if args.only.lower() in p.name.lower()]

    print(f"Found {len(pdfs)} PDF(s) in {PDF_DIR}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for pdf_path in pdfs:
        slug = sanitize_filename(pdf_path.name)
        out_path = OUT_DIR / f"{slug}.md"
        print(f"\nConverting: {pdf_path.name}")
        convert_pdf(pdf_path, out_path, split_pages=args.split_pages)

    print(f"\nDone! Markdown files written to {OUT_DIR}")


if __name__ == "__main__":
    main()
