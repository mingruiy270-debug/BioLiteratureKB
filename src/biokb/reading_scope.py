"""Explicit PDF reading scope: never stop at References before later Methods."""
import re


def parse_text_pages(selection: str, total: int) -> list[int]:
    if selection == "all":
        return list(range(1,total+1))
    selected = set()
    for part in selection.split(','):
        match = re.fullmatch(r"\s*(\d+)(?:-(\d+))?\s*",part)
        if not match:
            raise ValueError("text-pages must be all or 1-based ranges, e.g. 1-12,15-20")
        start = int(match[1]); end = int(match[2] or match[1])
        if not 1 <= start <= end <= total:
            raise ValueError("text-pages range outside PDF")
        values = set(range(start,end+1))
        if selected & values:
            raise ValueError("text-pages contains duplicate/overlapping pages")
        selected.update(values)
    return sorted(selected)
