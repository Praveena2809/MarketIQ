from typing import List
from app.core.config import get_settings


class ChunkingService:
    def __init__(self, chunk_size: int = None, chunk_overlap: int = None):
        settings = get_settings()
        self.chunk_size = chunk_size or settings.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP

    def chunk_text(self, text: str) -> List[str]:
        """
        Split text into overlapping chunks preserving paragraph and sentence boundaries where possible.
        """
        if not text or not text.strip():
            return []

        cleaned_text = text.strip()
        if len(cleaned_text) <= self.chunk_size:
            return [cleaned_text]

        paragraphs = [p.strip() for p in cleaned_text.split("\n\n") if p.strip()]
        chunks: List[str] = []
        current_chunk: List[str] = []
        current_length = 0

        for para in paragraphs:
            para_len = len(para)
            if para_len > self.chunk_size:
                # Paragraph itself exceeds chunk size, split by lines or sentences
                lines = [l.strip() for l in para.split("\n") if l.strip()]
                for line in lines:
                    line_len = len(line)
                    if current_length + line_len + 1 > self.chunk_size and current_chunk:
                        chunk_str = "\n".join(current_chunk).strip()
                        if chunk_str:
                            chunks.append(chunk_str)
                        # Retain overlap from end of previous chunk
                        current_chunk = self._get_overlap_tokens(current_chunk)
                        current_length = sum(len(c) + 1 for c in current_chunk)
                    current_chunk.append(line)
                    current_length += line_len + 1
            else:
                if current_length + para_len + 2 > self.chunk_size and current_chunk:
                    chunk_str = "\n\n".join(current_chunk).strip()
                    if chunk_str:
                        chunks.append(chunk_str)
                    current_chunk = self._get_overlap_tokens(current_chunk)
                    current_length = sum(len(c) + 2 for c in current_chunk)

                current_chunk.append(para)
                current_length += para_len + 2

        if current_chunk:
            final_chunk = "\n\n".join(current_chunk).strip()
            if final_chunk:
                chunks.append(final_chunk)

        return chunks

    def _get_overlap_tokens(self, pieces: List[str]) -> List[str]:
        """Keep recent pieces that fit within the chunk_overlap limit."""
        overlap_pieces = []
        accumulated = 0
        for p in reversed(pieces):
            if accumulated + len(p) <= self.chunk_overlap:
                overlap_pieces.insert(0, p)
                accumulated += len(p)
            else:
                break
        return overlap_pieces
