"""
RAG pipeline over kidney clinical guideline PDFs.

Build index once at import time; search is read-only and thread-safe.
"""

from __future__ import annotations

import hashlib
import os
import pickle
import sys
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import fitz  # PyMuPDF
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Data directory (resolved relative to this file so the server can be run
# from any cwd).
# ---------------------------------------------------------------------------
_DATA_DIR = Path(__file__).parent.parent / "data" / "Kidney v1 Clinical Guidelines"
_CACHE_DIR = Path(__file__).parent.parent / "cache"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
_MODEL_NAME = "all-MiniLM-L6-v2"
_CHUNK_SIZE = 600        # characters
_CHUNK_OVERLAP = 120     # characters


@dataclass
class Chunk:
    text: str
    source: str
    page: int


# ---------------------------------------------------------------------------
# PDF ingestion
# ---------------------------------------------------------------------------

def _extract_pages(pdf_path: Path) -> List[tuple[int, str]]:
    """Return list of (page_number_1indexed, text) for every page."""
    pages = []
    with fitz.open(str(pdf_path)) as doc:
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text")
            if text.strip():
                pages.append((i, text))
    return pages


def _split_into_chunks(text: str, page: int, source: str) -> List[Chunk]:
    """
    Prefer splitting on double-newlines (section breaks); fall back to a
    fixed-size sliding window when sections are too large.
    """
    # Normalise whitespace
    text = re.sub(r"\n{3,}", "\n\n", text.strip())

    # Try semantic split on double newlines
    raw_sections = re.split(r"\n\n+", text)
    chunks: List[Chunk] = []
    buffer = ""

    for section in raw_sections:
        section = section.strip()
        if not section:
            continue
        if len(buffer) + len(section) <= _CHUNK_SIZE:
            buffer = (buffer + "\n\n" + section).strip()
        else:
            if buffer:
                chunks.append(Chunk(text=buffer, source=source, page=page))
            # If section itself is too large, slide a window over it
            if len(section) > _CHUNK_SIZE:
                for start in range(0, len(section), _CHUNK_SIZE - _CHUNK_OVERLAP):
                    part = section[start : start + _CHUNK_SIZE]
                    if part.strip():
                        chunks.append(Chunk(text=part.strip(), source=source, page=page))
                buffer = ""
            else:
                buffer = section

    if buffer:
        chunks.append(Chunk(text=buffer, source=source, page=page))

    return chunks


def _load_all_chunks(data_dir: Path) -> List[Chunk]:
    all_chunks: List[Chunk] = []
    pdf_files = sorted(data_dir.glob("*.pdf"))
    if not pdf_files:
        raise FileNotFoundError(f"No PDF files found in {data_dir}")
    for pdf_path in pdf_files:
        pages = _extract_pages(pdf_path)
        for page_num, page_text in pages:
            chunks = _split_into_chunks(page_text, page_num, pdf_path.name)
            all_chunks.extend(chunks)
    return all_chunks


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

def _pdf_cache_key(data_dir: Path) -> str:
    """Hash of sorted (name, mtime, size) for all PDFs — changes when PDFs change."""
    pdf_files = sorted(data_dir.glob("*.pdf"))
    fingerprint = "|".join(
        f"{p.name}:{p.stat().st_mtime}:{p.stat().st_size}" for p in pdf_files
    )
    return hashlib.sha256(fingerprint.encode()).hexdigest()[:16]


class KidneyRAG:
    """Singleton-style RAG index. Build once, query many times."""

    def __init__(self, data_dir: Path = _DATA_DIR) -> None:
        print(f"[kidney-rag] Loading embedding model '{_MODEL_NAME}' …", file=sys.stderr, flush=True)
        self._model = SentenceTransformer(_MODEL_NAME)

        _CACHE_DIR.mkdir(exist_ok=True)
        key = _pdf_cache_key(data_dir)
        key_file    = _CACHE_DIR / "cache_key.txt"
        chunks_file = _CACHE_DIR / "chunks.pkl"
        index_file  = _CACHE_DIR / "index.faiss"

        if (key_file.exists() and chunks_file.exists() and index_file.exists()
                and key_file.read_text().strip() == key):
            print("[kidney-rag] Loading from cache …", file=sys.stderr, flush=True)
            with open(chunks_file, "rb") as f:
                self._chunks = pickle.load(f)
            self._index = faiss.read_index(str(index_file))
            print(f"[kidney-rag] {len(self._chunks)} chunks restored from cache.", file=sys.stderr, flush=True)
        else:
            print(f"[kidney-rag] Loading PDFs from {data_dir} …", file=sys.stderr, flush=True)
            self._chunks = _load_all_chunks(data_dir)
            print(f"[kidney-rag] {len(self._chunks)} chunks from "
                  f"{len(set(c.source for c in self._chunks))} PDF(s)", file=sys.stderr, flush=True)

            print("[kidney-rag] Building FAISS index …", file=sys.stderr, flush=True)
            texts = [c.text for c in self._chunks]
            embeddings = self._model.encode(texts, show_progress_bar=False, batch_size=64)
            embeddings = np.array(embeddings, dtype="float32")

            dim = embeddings.shape[1]
            self._index = faiss.IndexFlatIP(dim)
            faiss.normalize_L2(embeddings)
            self._index.add(embeddings)

            print("[kidney-rag] Saving cache …", file=sys.stderr, flush=True)
            with open(chunks_file, "wb") as f:
                pickle.dump(self._chunks, f)
            faiss.write_index(self._index, str(index_file))
            key_file.write_text(key)
            print("[kidney-rag] Index ready.", file=sys.stderr, flush=True)

    def search(self, query: str, k: int = 5) -> List[dict]:
        """Return top-k chunks as dicts with text / source / page keys."""
        q_vec = self._model.encode([query], show_progress_bar=False)
        q_vec = np.array(q_vec, dtype="float32")
        faiss.normalize_L2(q_vec)

        scores, indices = self._index.search(q_vec, k)
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            chunk = self._chunks[idx]
            results.append({
                "text": chunk.text,
                "source": chunk.source,
                "page": chunk.page,
                "score": float(score),
            })
        return results


# ---------------------------------------------------------------------------
# Module-level singleton — built once when the server starts
# ---------------------------------------------------------------------------
_rag: KidneyRAG | None = None


def get_rag() -> KidneyRAG:
    global _rag
    if _rag is None:
        _rag = KidneyRAG()
    return _rag


def search_kidney_guidelines(query: str, k: int = 5) -> dict:
    rag = get_rag()
    results = rag.search(query, k=k)
    return {
        "query": query,
        "results": [
            {"text": r["text"], "source": r["source"], "page": r["page"]}
            for r in results
        ],
    }
