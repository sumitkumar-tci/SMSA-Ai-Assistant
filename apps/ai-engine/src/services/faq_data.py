"""
FAQ Data Loader - Loads scraped FAQ data from JSONL file.

In production, this will be replaced by Vector DB RAG pipeline.
For now, we load the JSONL file and use it as context for FAQ agent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from ..logging_config import logger

# Path to FAQ data file
FAQ_DATA_PATH = Path(__file__).parent.parent.parent.parent / "data_for_faq" / "smsa_chunks.jsonl"


class SMSAAIAssistantFAQDataLoader:
    """
    Loads and manages FAQ data from JSONL file.
    
    In production, this will be replaced by Vector DB semantic search.
    """

    def __init__(self) -> None:
        self._chunks: List[Dict[str, Any]] = []
        self._loaded = False

    def _load_chunks(self) -> List[Dict[str, Any]]:
        """Load FAQ chunks from JSONL file."""
        if not FAQ_DATA_PATH.exists():
            logger.warning("faq_data_file_not_found", path=str(FAQ_DATA_PATH))
            return []

        chunks: List[Dict[str, Any]] = []
        try:
            with open(FAQ_DATA_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        chunks.append(chunk)
                    except json.JSONDecodeError as e:
                        logger.warning("faq_chunk_parse_error", error=str(e))
                        continue

            logger.info("faq_data_loaded", chunks_count=len(chunks))
            return chunks
        except Exception as e:
            logger.error("faq_data_load_error", error=str(e), exc_info=True)
            return []

    def get_chunks(self) -> List[Dict[str, Any]]:
        """Get all FAQ chunks (lazy loading)."""
        if not self._loaded:
            self._chunks = self._load_chunks()
            self._loaded = True
        return self._chunks

    def search_relevant_chunks(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Simple keyword-based search for relevant chunks.
        
        In production, this will use Vector DB semantic search.
        For now, we do simple keyword matching.
        
        Args:
            query: User query
            top_k: Number of chunks to return
            
        Returns:
            List of relevant chunks
        """
        chunks = self.get_chunks()
        if not chunks:
            return []

        query_lower = query.lower()
        scored_chunks: List[tuple[float, Dict[str, Any]]] = []

        for chunk in chunks:
            chunk_text = chunk.get("chunk_text", "").lower()
            title = chunk.get("title", "").lower()
            
            # Simple scoring: count keyword matches
            score = 0
            for word in query_lower.split():
                if word in chunk_text:
                    score += chunk_text.count(word)
                if word in title:
                    score += title.count(word) * 2  # Title matches are more important

            if score > 0:
                scored_chunks.append((score, chunk))

        # Sort by score (descending) and return top_k
        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        return [chunk for _, chunk in scored_chunks[:top_k]]

    def get_context_for_llm(self, query: str, max_chunks: int = 3) -> str:
        """
        Get formatted context string for LLM prompt.
        
        Args:
            query: User query
            max_chunks: Maximum number of chunks to include
            
        Returns:
            Formatted context string
        """
        relevant_chunks = self.search_relevant_chunks(query, top_k=max_chunks)
        
        if not relevant_chunks:
            return ""

        context_parts: List[str] = []
        for i, chunk in enumerate(relevant_chunks, 1):
            chunk_text = chunk.get("chunk_text", "").strip()
            title = chunk.get("title", "")
            url = chunk.get("url", "")
            
            if chunk_text:
                context_parts.append(f"[Reference {i}]")
                if title:
                    context_parts.append(f"Title: {title}")
                if url:
                    context_parts.append(f"Source: {url}")
                context_parts.append(f"Content: {chunk_text[:500]}...")  # Limit length
                context_parts.append("")

        return "\n".join(context_parts)


# Global instance
_faq_data_loader: SMSAAIAssistantFAQDataLoader | None = None


def get_faq_data_loader() -> SMSAAIAssistantFAQDataLoader:
    """Get global FAQ data loader instance."""
    global _faq_data_loader
    if _faq_data_loader is None:
        _faq_data_loader = SMSAAIAssistantFAQDataLoader()
    return _faq_data_loader
