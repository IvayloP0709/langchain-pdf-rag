#!/usr/bin/env python3
"""Bulk-download arXiv PDFs for a focused RAG corpus.

Usage example:
python scripts/download_arxiv_pdfs.py \
  --query "cat:cs.AI AND (all:retrieval OR all:RAG OR all:agents)" \
  --max-results 30 \
  --out-dir data/papers
"""

from __future__ import annotations

import argparse
import csv
import re
import ssl
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List
from urllib.parse import quote
from urllib.request import Request, urlopen

ARXIV_API_URL = "https://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
USER_AGENT = "langchain-pdf-rag/1.0 (portfolio project)"


@dataclass
class ArxivPaper:
    arxiv_id: str
    title: str
    published: str
    updated: str
    authors: str
    summary: str
    abs_url: str
    pdf_url: str
    local_pdf: str = ""


def sanitize_filename(value: str, max_len: int = 110) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"[^A-Za-z0-9._ -]", "", value)
    value = value.replace("/", "-")
    if not value:
        return "paper"
    return value[:max_len].rstrip(" .")


def extract_arxiv_id(abs_url: str) -> str:
    paper_id = abs_url.rstrip("/").split("/")[-1]
    # Keep version if present (e.g., 2401.12345v2) for reproducibility.
    return paper_id


def parse_feed(xml_text: str) -> List[ArxivPaper]:
    root = ET.fromstring(xml_text)
    papers: List[ArxivPaper] = []

    for entry in root.findall("atom:entry", ATOM_NS):
        abs_url = ""
        pdf_url = ""

        for link in entry.findall("atom:link", ATOM_NS):
            rel = link.attrib.get("rel", "")
            title = link.attrib.get("title", "")
            href = link.attrib.get("href", "")
            if rel == "alternate" and href:
                abs_url = href
            if title == "pdf" and href:
                pdf_url = href

        # Fallback URL generation when feed omits explicit PDF link.
        if abs_url and not pdf_url:
            paper_id = extract_arxiv_id(abs_url)
            pdf_url = f"https://arxiv.org/pdf/{paper_id}.pdf"

        if not abs_url:
            continue

        title_text = (entry.findtext("atom:title", default="", namespaces=ATOM_NS) or "").strip()
        summary_text = (
            entry.findtext("atom:summary", default="", namespaces=ATOM_NS) or ""
        ).strip()
        published_text = entry.findtext("atom:published", default="", namespaces=ATOM_NS) or ""
        updated_text = entry.findtext("atom:updated", default="", namespaces=ATOM_NS) or ""

        author_names = []
        for author in entry.findall("atom:author", ATOM_NS):
            name = (author.findtext("atom:name", default="", namespaces=ATOM_NS) or "").strip()
            if name:
                author_names.append(name)

        papers.append(
            ArxivPaper(
                arxiv_id=extract_arxiv_id(abs_url),
                title=title_text,
                published=published_text,
                updated=updated_text,
                authors="; ".join(author_names),
                summary=summary_text,
                abs_url=abs_url,
                pdf_url=pdf_url,
            )
        )

    return papers


def build_ssl_context(insecure: bool = False, cafile: str | None = None) -> ssl.SSLContext:
    if insecure:
        return ssl._create_unverified_context()

    if cafile:
        return ssl.create_default_context(cafile=cafile)

    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        # Fallback to system trust store if certifi is unavailable.
        return ssl.create_default_context()


def fetch_arxiv_feed(
    query: str,
    start: int,
    max_results: int,
    sort_by: str,
    sort_order: str,
    ssl_context: ssl.SSLContext,
) -> List[ArxivPaper]:
    encoded_query = quote(query, safe='():" ')
    encoded_query = encoded_query.replace(" ", "+")
    url = (
        f"{ARXIV_API_URL}?search_query={encoded_query}"
        f"&start={start}&max_results={max_results}"
        f"&sortBy={sort_by}&sortOrder={sort_order}"
    )

    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=60, context=ssl_context) as response:
        xml_bytes = response.read()
    return parse_feed(xml_bytes.decode("utf-8", errors="replace"))


def download_file(
    url: str, destination: Path, ssl_context: ssl.SSLContext, retries: int = 3
) -> None:
    request = Request(url, headers={"User-Agent": USER_AGENT})

    for attempt in range(1, retries + 1):
        try:
            with urlopen(request, timeout=90, context=ssl_context) as response:
                destination.write_bytes(response.read())
            if destination.stat().st_size < 1024:
                raise RuntimeError("Downloaded file is unexpectedly small")
            return
        except Exception:
            if destination.exists():
                destination.unlink(missing_ok=True)
            if attempt >= retries:
                raise
            time.sleep(1.0 * attempt)


def load_existing_metadata(csv_path: Path) -> Dict[str, Dict[str, str]]:
    if not csv_path.exists():
        return {}

    rows: Dict[str, Dict[str, str]] = {}
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            paper_id = row.get("arxiv_id", "").strip()
            if paper_id:
                rows[paper_id] = row
    return rows


def write_metadata(csv_path: Path, rows: Iterable[Dict[str, str]]) -> None:
    fieldnames = [
        "arxiv_id",
        "title",
        "authors",
        "published",
        "updated",
        "abs_url",
        "pdf_url",
        "local_pdf",
        "summary",
    ]
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def paper_to_row(paper: ArxivPaper) -> Dict[str, str]:
    return {
        "arxiv_id": paper.arxiv_id,
        "title": paper.title,
        "authors": paper.authors,
        "published": paper.published,
        "updated": paper.updated,
        "abs_url": paper.abs_url,
        "pdf_url": paper.pdf_url,
        "local_pdf": paper.local_pdf,
        "summary": paper.summary,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download arXiv PDFs into data/papers with metadata."
    )
    parser.add_argument(
        "--query",
        action="append",
        required=True,
        help=(
            "arXiv API query. Repeat this flag for multiple topic pulls. "
            "Example: --query 'cat:cs.AI AND (all:retrieval OR all:RAG)'"
        ),
    )
    parser.add_argument("--start", type=int, default=0, help="Pagination start index.")
    parser.add_argument("--max-results", type=int, default=30, help="Results per query.")
    parser.add_argument(
        "--sort-by",
        choices=["relevance", "lastUpdatedDate", "submittedDate"],
        default="relevance",
        help="Sort strategy in arXiv API.",
    )
    parser.add_argument(
        "--sort-order",
        choices=["ascending", "descending"],
        default="descending",
        help="Sort order in arXiv API.",
    )
    parser.add_argument("--out-dir", default="data/papers", help="Directory where PDFs are stored.")
    parser.add_argument(
        "--metadata",
        default="data/papers/metadata.csv",
        help="Metadata CSV output path.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=1.5,
        help="Delay between PDF downloads to be polite to arXiv.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip downloading a PDF when target filename already exists.",
    )
    parser.add_argument(
        "--cafile",
        default=None,
        help="Path to custom CA bundle PEM file for SSL verification.",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable SSL certificate verification (last resort for local troubleshooting).",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    ssl_context = build_ssl_context(insecure=args.insecure, cafile=args.cafile)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = Path(args.metadata)

    existing = load_existing_metadata(metadata_path)
    discovered: Dict[str, ArxivPaper] = {}

    for query in args.query:
        print(f"Fetching query: {query}")
        papers = fetch_arxiv_feed(
            query=query,
            start=args.start,
            max_results=args.max_results,
            sort_by=args.sort_by,
            sort_order=args.sort_order,
            ssl_context=ssl_context,
        )
        print(f"  Found {len(papers)} papers")

        for paper in papers:
            discovered[paper.arxiv_id] = paper

    downloaded = 0
    skipped = 0
    failed = 0

    for paper in discovered.values():
        filename = sanitize_filename(f"{paper.arxiv_id}_{paper.title}") + ".pdf"
        destination = out_dir / filename
        paper.local_pdf = str(destination).replace("\\", "/")

        if destination.exists() and args.skip_existing:
            skipped += 1
            continue

        try:
            download_file(paper.pdf_url, destination, ssl_context=ssl_context)
            downloaded += 1
            time.sleep(max(args.delay_seconds, 0.0))
        except Exception as exc:
            failed += 1
            print(f"  Failed: {paper.arxiv_id} -> {exc}")

    merged_rows: Dict[str, Dict[str, str]] = dict(existing)
    for paper in discovered.values():
        merged_rows[paper.arxiv_id] = paper_to_row(paper)

    # Stable ordering by published date descending when possible.
    sorted_rows = sorted(
        merged_rows.values(),
        key=lambda row: row.get("published", ""),
        reverse=True,
    )
    write_metadata(metadata_path, sorted_rows)

    print("\nSummary")
    print(f"  Unique papers discovered: {len(discovered)}")
    print(f"  Downloaded: {downloaded}")
    print(f"  Skipped existing: {skipped}")
    print(f"  Failed: {failed}")
    print(f"  Metadata written: {metadata_path}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
