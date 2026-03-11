"""RAG service: knowledge base indexing, embedding, and retrieval via ChromaDB."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import chromadb
from openai import AsyncOpenAI

from src.config import RAGConfig

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """A single retrieval result from the knowledge base."""

    content: str
    source: str
    section: str
    score: float


class KnowledgeBase:
    """Indexes markdown documents and provides semantic search via ChromaDB.

    Usage::

        kb = KnowledgeBase(config, openai_client)
        await kb.initialize()
        results = await kb.search("What is the pricing?")
    """

    def __init__(
        self,
        config: RAGConfig | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._config = config or RAGConfig()
        self._client = client or AsyncOpenAI()
        self._chroma_client: chromadb.ClientAPI | None = None
        self._collection: chromadb.Collection | None = None

    async def initialize(self) -> None:
        """Read markdown files, chunk them, embed, and store in ChromaDB.

        Skips re-indexing if the knowledge base files haven't changed
        since the last run (checked via content hash).
        """
        data_dir = Path(self._config.data_dir)
        if not data_dir.exists():
            logger.warning("Knowledge base directory not found: %s", data_dir)
            return

        # Compute hash of all knowledge base files.
        current_hash = self._compute_files_hash(data_dir)

        # Set up ChromaDB persistent client.
        chroma_path = Path(self._config.chroma_dir)
        chroma_path.mkdir(parents=True, exist_ok=True)
        self._chroma_client = chromadb.PersistentClient(path=str(chroma_path))
        self._collection = self._chroma_client.get_or_create_collection(
            name="knowledge_base",
            metadata={"hnsw:space": "cosine"},
        )

        # Check if re-indexing is needed.
        stored_hash = self._collection.metadata.get("files_hash", "")
        if stored_hash == current_hash and self._collection.count() > 0:
            logger.info(
                "Knowledge base unchanged (%d chunks indexed), skipping re-index",
                self._collection.count(),
            )
            return

        # Re-index: clear existing data and re-process all files.
        logger.info("Indexing knowledge base from %s ...", data_dir)
        if self._collection.count() > 0:
            # Delete all existing documents.
            all_ids = self._collection.get()["ids"]
            if all_ids:
                self._collection.delete(ids=all_ids)

        chunks = self._chunk_all_files(data_dir)
        if not chunks:
            logger.warning("No chunks extracted from knowledge base")
            return

        # Embed all chunks.
        texts = [c["content"] for c in chunks]
        embeddings = await self._embed_texts(texts)

        # Store in ChromaDB.
        ids = [f"chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {"source": c["source"], "section": c["section"]}
            for c in chunks
        ]
        self._collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

        # Update the collection metadata with the files hash.
        # Note: cannot re-set hnsw:space after creation, only set custom metadata.
        self._collection.modify(metadata={
            "files_hash": current_hash,
        })

        logger.info("Indexed %d chunks from %d files", len(chunks), len(list(data_dir.glob("*.md"))))

    async def search(
        self,
        query: str,
        n_results: int | None = None,
    ) -> list[RetrievalResult]:
        """Search the knowledge base for chunks relevant to the query."""
        if self._collection is None or self._collection.count() == 0:
            logger.warning("Knowledge base not initialized or empty")
            return []

        n = n_results or self._config.search_results
        query_embedding = await self._embed_texts([query])

        results = self._collection.query(
            query_embeddings=query_embedding,
            n_results=min(n, self._collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        retrieval_results = []
        for i in range(len(results["ids"][0])):
            # ChromaDB cosine distance: 0 = identical, 2 = opposite.
            distance = results["distances"][0][i]
            score = 1.0 - (distance / 2.0)  # Convert to 0-1 similarity.
            retrieval_results.append(RetrievalResult(
                content=results["documents"][0][i],
                source=results["metadatas"][0][i]["source"],
                section=results["metadatas"][0][i]["section"],
                score=score,
            ))

        logger.debug("Search for %r returned %d results", query, len(retrieval_results))
        return retrieval_results

    def get_source_details(self, document_id: str) -> dict:
        """Return metadata about a source document in the knowledge base."""
        if self._collection is None or self._collection.count() == 0:
            return {"error": "Knowledge base not initialized"}

        # Find all chunks from this source file.
        results = self._collection.get(
            where={"source": document_id},
            include=["metadatas"],
        )

        if not results["ids"]:
            return {"error": f"Document '{document_id}' not found in knowledge base"}

        sections = sorted({m["section"] for m in results["metadatas"]})
        return {
            "document": document_id,
            "total_chunks": len(results["ids"]),
            "sections": sections,
        }

    def list_documents(self) -> list[str]:
        """Return a list of all source document filenames in the knowledge base."""
        if self._collection is None or self._collection.count() == 0:
            return []

        results = self._collection.get(include=["metadatas"])
        return sorted({m["source"] for m in results["metadatas"]})

    # -- Private helpers ------------------------------------------------------

    def _compute_files_hash(self, data_dir: Path) -> str:
        """Compute a combined SHA-256 hash of all markdown files."""
        hasher = hashlib.sha256()
        for filepath in sorted(data_dir.glob("*.md")):
            hasher.update(filepath.name.encode())
            hasher.update(filepath.read_bytes())
        return hasher.hexdigest()

    def _chunk_all_files(self, data_dir: Path) -> list[dict]:
        """Read and chunk all markdown files in the data directory."""
        chunks = []
        for filepath in sorted(data_dir.glob("*.md")):
            file_chunks = self._chunk_markdown(
                filepath.read_text(encoding="utf-8"),
                filepath.name,
            )
            chunks.extend(file_chunks)
        return chunks

    def _chunk_markdown(self, text: str, filename: str) -> list[dict]:
        """Split markdown text into chunks by H2 sections.

        Each chunk carries metadata about the source file and section title.
        Chunks exceeding ``chunk_max_chars`` are further split at paragraph
        boundaries.
        """
        max_chars = self._config.chunk_max_chars
        chunks = []

        # Split by H2 headers.
        sections = re.split(r"(?=^## )", text, flags=re.MULTILINE)

        for section in sections:
            section = section.strip()
            if not section:
                continue

            # Extract section title.
            lines = section.split("\n", 1)
            title_line = lines[0].strip()
            # Remove markdown heading markers.
            section_title = re.sub(r"^#+\s*", "", title_line)

            if len(section) <= max_chars:
                chunks.append({
                    "content": section,
                    "source": filename,
                    "section": section_title,
                })
            else:
                # Split large sections at paragraph boundaries.
                paragraphs = re.split(r"\n\n+", section)
                current_chunk = ""
                for para in paragraphs:
                    if current_chunk and len(current_chunk) + len(para) > max_chars:
                        chunks.append({
                            "content": current_chunk.strip(),
                            "source": filename,
                            "section": section_title,
                        })
                        current_chunk = para
                    else:
                        current_chunk += ("\n\n" + para) if current_chunk else para
                if current_chunk.strip():
                    chunks.append({
                        "content": current_chunk.strip(),
                        "source": filename,
                        "section": section_title,
                    })

        return chunks

    async def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts using OpenAI API."""
        # OpenAI embeddings API supports batching (up to 2048 texts).
        response = await self._client.embeddings.create(
            model=self._config.embedding_model,
            input=texts,
        )
        return [item.embedding for item in response.data]
