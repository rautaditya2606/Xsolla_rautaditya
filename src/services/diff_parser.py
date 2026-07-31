from typing import NamedTuple
from unidiff import PatchSet, UnidiffParseError

class AddedLine(NamedTuple):
    path: str
    line: int
    content: str  # content without leading '+'

class ParsedFile(NamedTuple):
    path: str
    raw_diff: str
    added_lines: list[AddedLine]

def is_valid_diff(diff_text: str) -> bool:
    """
    Validates if diff_text can be parsed as a unified diff using unidiff.
    """
    if not diff_text or not isinstance(diff_text, str) or not diff_text.strip():
        return False
    try:
        patch = PatchSet.from_string(diff_text)
        return len(patch) > 0
    except (UnidiffParseError, Exception):
        return False

def parse_unified_diff(diff_text: str) -> list[ParsedFile]:
    """
    Parses unified diff string into ParsedFile structures using unidiff.
    """
    if not is_valid_diff(diff_text):
        raise ValueError("Invalid unified diff format")

    patch = PatchSet.from_string(diff_text)
    parsed_files: list[ParsedFile] = []

    for patched_file in patch:
        target_path = patched_file.target_file
        if target_path.startswith("b/") or target_path.startswith("a/"):
            target_path = target_path[2:]
        elif target_path == "/dev/null" and patched_file.source_file:
            target_path = patched_file.source_file
            if target_path.startswith("a/") or target_path.startswith("b/"):
                target_path = target_path[2:]

        added_lines: list[AddedLine] = []
        raw_diff_lines: list[str] = [str(patched_file)]

        for hunk in patched_file:
            for line in hunk:
                if line.is_added and line.target_line_no is not None:
                    # Strip trailing newlines for content evaluation
                    content_clean = line.value.rstrip("\r\n")
                    added_lines.append(AddedLine(
                        path=target_path,
                        line=line.target_line_no,
                        content=content_clean
                    ))

        parsed_files.append(ParsedFile(
            path=target_path,
            raw_diff="".join(raw_diff_lines),
            added_lines=added_lines
        ))

    return parsed_files
