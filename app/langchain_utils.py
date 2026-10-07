"""LangChain utilities for DocuStream."""
from typing import List, Dict, Any
from langchain_text_splitters import RecursiveCharacterTextSplitter


class TextSplitter:
    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 100):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
        )

    def split_text(self, text: str) -> List[str]:
        if not text:
            return []
        return self.splitter.split_text(text)
