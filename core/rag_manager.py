import os
import json
import hashlib
from typing import List, Dict, Any
from pathlib import Path

from fastapi import UploadFile

# Optional: use langchain's text splitter if available
try:
    from langchain.text_splitter import RecursiveCharacterTextSplitter
except ImportError:
    RecursiveCharacterTextSplitter = None

# OpenAI for embeddings
try:
    import openai
except ImportError:
    openai = None

# Helper functions
def _ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)

def _load_json(file_path: Path) -> Any:
    if not file_path.is_file():
        return None
    with file_path.open("r", encoding="utf-8") as f:
        return json.load(f)

def _save_json(file_path: Path, data: Any):
    _ensure_dir(file_path.parent)
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    import math
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)

class RAGManager:
    """Lightweight per‑company RAG manager using JSON files.

    Data layout:
        data/companies.json          – registry of companies
        data/rag/{company_id}.json   – list of {"chunk_text": str, "embedding": [float], "metadata": dict}
    """

    def __init__(self, base_path: str = "data"):
        self.base_path = Path(base_path)
        self.companies_path = self.base_path / "companies.json"
        self.rag_dir = self.base_path / "rag"
        _ensure_dir(self.base_path)
        _ensure_dir(self.rag_dir)
        # Load registry lazily
        self._companies_cache: Dict[str, Dict[str, Any]] = {}
        self._load_companies()
        # Simple in‑memory cache for embeddings per company
        self._rag_cache: Dict[str, List[Dict[str, Any]]] = {}

    # ---------------------------------------------------------------------
    # Company registry helpers
    # ---------------------------------------------------------------------
    def _load_companies(self):
        data = _load_json(self.companies_path)
        if isinstance(data, dict):
            self._companies_cache = data
        else:
            self._companies_cache = {}

    def _save_companies(self):
        _save_json(self.companies_path, self._companies_cache)

    def add_company(self, company_id: str, metadata: Dict[str, Any]):
        if company_id in self._companies_cache:
            raise ValueError(f"Company {company_id} already exists")
        self._companies_cache[company_id] = metadata
        self._save_companies()
        # Create empty rag file
        rag_path = self.rag_dir / f"{company_id}.json"
        _save_json(rag_path, [])

    def remove_company(self, company_id: str):
        self._companies_cache.pop(company_id, None)
        self._save_companies()
        rag_path = self.rag_dir / f"{company_id}.json"
        if rag_path.is_file():
            rag_path.unlink()
        self._rag_cache.pop(company_id, None)

    def get_company(self, company_id: str) -> Dict[str, Any] | None:
        return self._companies_cache.get(company_id)

    def list_companies(self) -> List[Dict[str, Any]]:
        return [{"company_id": cid, **meta} for cid, meta in self._companies_cache.items()]

    # ---------------------------------------------------------------------
    # Document handling
    # ---------------------------------------------------------------------
    def _read_rag_file(self, company_id: str) -> List[Dict[str, Any]]:
        if company_id in self._rag_cache:
            return self._rag_cache[company_id]
        rag_path = self.rag_dir / f"{company_id}.json"
        data = _load_json(rag_path)
        if not isinstance(data, list):
            data = []
        self._rag_cache[company_id] = data
        return data

    def _write_rag_file(self, company_id: str, data: List[Dict[str, Any]]):
        rag_path = self.rag_dir / f"{company_id}.json"
        _save_json(rag_path, data)
        self._rag_cache[company_id] = data

    def _split_text(self, text: str) -> List[str]:
        if RecursiveCharacterTextSplitter:
            splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
            return splitter.split_text(text)
        # Fallback simple split
        return [text[i : i + 500] for i in range(0, len(text), 500)]

    async def _embed_text(self, text: str) -> List[float]:
        if not openai:
            raise RuntimeError("openai package not installed")
        response = await openai.Embedding.acreate(
            model="text-embedding-ada-002",
            input=text,
        )
        return response["data"][0]["embedding"]

    async def upload_documents(self, company_id: str, files: List[UploadFile]):
        """Chunk uploaded files, generate embeddings, and store them.
        Supported file types: plain text (.txt) and PDFs (.pdf). PDF handling falls back to raw bytes -> text conversion via PyPDF2 if available.
        """
        existing = self._read_rag_file(company_id)
        for upload in files:
            content = await upload.read()
            # Determine simple text extraction based on filename extension
            filename = upload.filename.lower()
            if filename.endswith('.txt'):
                text = content.decode('utf-8', errors='ignore')
            else:
                # Try PDF extraction
                try:
                    import PyPDF2
                    pdf_reader = PyPDF2.PdfReader(upload.file)
                    text = "\n".join(page.extract_text() or "" for page in pdf_reader.pages)
                except Exception:
                    # Fallback to raw bytes as string
                    text = content.decode('utf-8', errors='ignore')
            chunks = self._split_text(text)
            for chunk in chunks:
                embedding = await self._embed_text(chunk)
                existing.append({
                    "chunk_text": chunk,
                    "embedding": embedding,
                    "metadata": {"source": upload.filename},
                })
        self._write_rag_file(company_id, existing)

    # ---------------------------------------------------------------------
    # Search
    # ---------------------------------------------------------------------
    async def search(self, company_id: str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if not openai:
            raise RuntimeError("openai package not installed")
        rag_data = self._read_rag_file(company_id)
        if not rag_data:
            return []
        query_emb = await self._embed_text(query)
        # Compute similarity scores
        scored = []
        for entry in rag_data:
            sim = _cosine_similarity(query_emb, entry["embedding"])
            scored.append((sim, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [e for _, e in scored[:top_k]]
        return top
