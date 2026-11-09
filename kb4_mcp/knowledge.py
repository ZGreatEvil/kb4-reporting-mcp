"""Background knowledge from official NIST publications, searched by keyword.

Build (downloads the PDFs, about 12 MB, and writes knowledge/nist_index.json):
    python -m kb4_mcp.knowledge

The search is BM25 over ~180-word passages that keep their page numbers, so answers can cite
"NIST SP 800-50r1, p. 14". No embedding model is needed; queries should be in English
because the documents are.
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_DIR = ROOT / "knowledge"
INDEX_FILE = KNOWLEDGE_DIR / "nist_index.json"

SOURCES = [
    {
        "id": "SP 800-50r1",
        "title": "NIST SP 800-50 Rev. 1: Building a Cybersecurity and Privacy Learning Program (2024)",
        "url": "https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-50r1.pdf",
    },
    {
        "id": "CSF 2.0",
        "title": "NIST Cybersecurity Framework (CSF) 2.0, CSWP 29 (2024)",
        "url": "https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf",
    },
    {
        "id": "TN 2276",
        "title": "NIST TN 2276: The NIST Phish Scale (2023)",
        "url": "https://nvlpubs.nist.gov/nistpubs/TechnicalNotes/NIST.TN.2276.pdf",
    },
]

PASSAGE_WORDS = 180
OVERLAP_WORDS = 40
STOPWORDS = set(
    "a an the and or of to in on for with by is are was were be been as at it its this that these those from "
    "can may should must will would not no do does how what which who why when where into than then also such "
    "their they them our we you your i".split()
)


def _tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS and len(w) > 1]


def _clean(text: str) -> str:
    text = re.sub(r"-\n(\w)", r"\1", text)  # words split across lines
    text = text.replace("�", " ")  # bullets and quotes pypdf cannot map
    return re.sub(r"\s+", " ", text).strip()


def _passages(pages: list[str]) -> list[dict[str, Any]]:
    out = []
    for page_no, text in enumerate(pages, 1):
        words = _clean(text).split()
        step = PASSAGE_WORDS - OVERLAP_WORDS
        for start in range(0, max(len(words), 1), step):
            chunk = words[start: start + PASSAGE_WORDS]
            if len(chunk) >= 25:
                out.append({"page": page_no, "text": " ".join(chunk)})
            if start + PASSAGE_WORDS >= len(words):
                break
    return out


class BuildError(RuntimeError):
    """a readable reason the library could not be built"""


def build_index(download: bool = True) -> dict[str, Any]:
    import httpx
    from pypdf import PdfReader

    pdf_dir = KNOWLEDGE_DIR / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    passages = []
    for source in SOURCES:
        pdf = pdf_dir / source["url"].rsplit("/", 1)[-1]
        if not pdf.exists():
            if not download:
                raise BuildError(f"{pdf.name} is not in {pdf_dir}. Put it there, or run without --no-download.")
            print(f"downloading {source['url']}", flush=True)
            # written under another name first, so a broken download never looks like a finished pdf
            part = pdf.with_suffix(".part")
            try:
                with httpx.stream("GET", source["url"], follow_redirects=True, timeout=120) as r:
                    r.raise_for_status()
                    with part.open("wb") as f:
                        for block in r.iter_bytes():
                            f.write(block)
            except httpx.HTTPError as exc:
                part.unlink(missing_ok=True)
                raise BuildError(f"Could not download {source['url']} ({type(exc).__name__}). Check the connection and run again.") from None
            part.replace(pdf)
        try:
            reader = PdfReader(str(pdf))
        except Exception as exc:  # pypdf raises several types for a damaged file
            raise BuildError(f"{pdf.name} could not be read ({type(exc).__name__}). Delete it and run again to download it fresh.") from None
        pages = [(p.extract_text() or "") for p in reader.pages]
        doc_passages = _passages(pages)
        for p in doc_passages:
            passages.append({"source": source["id"], **p})
        print(f"{source['id']}: {len(reader.pages)} pages, {len(doc_passages)} passages", flush=True)

    index = {"sources": SOURCES, "passages": passages}
    INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    return {"passages": len(passages), "file": str(INDEX_FILE)}


class NistSearch:
    def __init__(self, index_file: Path = INDEX_FILE):
        self.index_file = index_file
        self._loaded = False

    def _load(self) -> None:
        data = json.loads(self.index_file.read_text(encoding="utf-8"))
        self.sources = {s["id"]: s for s in data["sources"]}
        self.passages = data["passages"]
        self.doc_tokens = [Counter(_tokens(p["text"])) for p in self.passages]
        self.lengths = [sum(c.values()) for c in self.doc_tokens]
        self.avg_len = sum(self.lengths) / max(len(self.lengths), 1)
        df: Counter = Counter()
        for c in self.doc_tokens:
            df.update(c.keys())
        n = len(self.passages)
        self.idf = {w: math.log(1 + (n - d + 0.5) / (d + 0.5)) for w, d in df.items()}
        self._loaded = True

    def search(self, query: str, limit: int = 4) -> dict[str, Any]:
        if not self.index_file.exists():
            return {"error": True, "message": "The NIST library is not set up. Run: python -m kb4_mcp.knowledge"}
        if not self._loaded:
            try:
                self._load()
            except (ValueError, KeyError, TypeError):
                return {"error": True, "message": "The NIST library index is damaged. Rebuild it: python -m kb4_mcp.knowledge"}
        terms = _tokens(query)
        if not terms:
            return {"query": query, "results": [], "note": "Use English keywords."}
        k1, b = 1.5, 0.75
        scored = []
        for i, counts in enumerate(self.doc_tokens):
            score = 0.0
            for w in terms:
                f = counts.get(w)
                if f:
                    score += self.idf.get(w, 0) * f * (k1 + 1) / (f + k1 * (1 - b + b * self.lengths[i] / self.avg_len))
            if score > 0:
                scored.append((score, i))
        scored.sort(reverse=True)
        results = []
        for score, i in scored[: max(1, min(int(limit or 4), 6))]:
            p = self.passages[i]
            results.append({"source": p["source"], "title": self.sources[p["source"]]["title"], "pdf_page": p["page"],
                            "score": round(score, 2), "text": p["text"]})
        return {
            "query": query,
            "results": results,
            "note": "Answer only from these passages and cite them as (source, PDF page N). If they do not answer the question, say so.",
        }


if __name__ == "__main__":
    try:
        print(build_index(download="--no-download" not in sys.argv))
    except BuildError as exc:
        sys.exit(str(exc))
