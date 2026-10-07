import re

_HAS_CONTENT = re.compile(r'\w')


def split_text(text: str, size: int = 800, overlap: int = 100) -> list[str]:
    if overlap >= size:
        raise ValueError('overlap must be smaller than size')

    text = text.replace('\r\n', '\n').strip()
    chunks: list[str] = []
    n = len(text)
    start = 0
    while start < n:
        end = min(start + size, n)
        if end < n:
            window = text[start:end]
            cut = max(window.rfind('\n\n'), window.rfind('\n'), window.rfind('. '), window.rfind(' '))
            if cut > size * 0.5:
                end = start + cut + 1
        piece = text[start:end].strip()
        if piece and _HAS_CONTENT.search(piece):
            chunks.append(piece)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks


def split_text_langchain(text, size: int = 800, overlap: int = 100):
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    if overlap >= size:
        raise ValueError('overlap must be smaller than size')
    text = text.replace('\r\n', '\n').strip()
    if not text or not _HAS_CONTENT.search(text):
        return []
    splitter = RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap, length_function=len)
    return splitter.split_text(text)
