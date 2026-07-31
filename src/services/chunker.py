from src.services.diff_parser import ParsedFile
from src.config import config

class DiffChunk:
    def __init__(self, index: int, files: list[ParsedFile]):
        self.index = index
        self.files = files
        self.byte_size = sum(len(f.raw_diff.encode("utf-8")) for f in files)

def chunk_parsed_files(parsed_files: list[ParsedFile], max_chunk_bytes: int = config.CHUNK_BYTES) -> list[DiffChunk]:
    """
    Sequential file boundary grouping of ParsedFile objects into chunks of at most max_chunk_bytes (64 KiB)
    strictly on file boundaries. Single files larger than max_chunk_bytes form their own chunk.
    """
    if not parsed_files:
        return []

    chunks: list[DiffChunk] = []
    current_files: list[ParsedFile] = []
    current_bytes: int = 0

    for file in parsed_files:
        file_bytes = len(file.raw_diff.encode("utf-8"))

        # Single file larger than max_chunk_bytes
        if file_bytes >= max_chunk_bytes:
            if current_files:
                chunks.append(DiffChunk(len(chunks), current_files))
                current_files = []
                current_bytes = 0
            chunks.append(DiffChunk(len(chunks), [file]))
            continue

        if current_bytes + file_bytes > max_chunk_bytes and current_files:
            chunks.append(DiffChunk(len(chunks), current_files))
            current_files = [file]
            current_bytes = file_bytes
        else:
            current_files.append(file)
            current_bytes += file_bytes

    if current_files:
        chunks.append(DiffChunk(len(chunks), current_files))

    return chunks
