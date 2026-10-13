"""Opt-in local OCR for sparse pages. No downloads, paid calls, or source edits."""
from dataclasses import dataclass
from pathlib import Path
import math
import re


@dataclass(frozen=True)
class OCRSettings:
    tessdata: str
    language: str = "eng"
    dpi: int = 300

    def contract(self) -> dict:
        if not re.fullmatch(r"[A-Za-z0-9_]+(?:\+[A-Za-z0-9_]+)*", self.language):
            raise ValueError("OCR language must name local traineddata files, e.g. eng or eng+deu")
        if type(self.dpi) is not int or not 72 <= self.dpi <= 400:
            raise ValueError("OCR dpi must be an integer in 72..400")
        folder = Path(self.tessdata).resolve()
        files = []
        for lang in self.language.split('+'):
            path = (folder / f"{lang}.traineddata").resolve()
            if not path.is_file():
                raise ValueError(f"Missing local OCR language data: {path}; no automatic download")
            s = path.stat()
            files.append(dict(path=str(path), size=s.st_size, mtime_ns=s.st_mtime_ns))
        return dict(tessdata=str(folder), language=self.language, dpi=self.dpi, language_files=files)


def recognize_sparse_page(page, settings: OCRSettings) -> dict:
    # Limit render memory. OCR quality remains unverified; no claim of checkbox
    # semantics, mathematical structure or guaranteed reading order.
    dpi = min(settings.dpi, int(72 * math.sqrt(20_000_000 / max(1, page.rect.get_area()))))
    if dpi < 72:
        raise ValueError("Page too large for bounded local OCR rendering")
    tp = page.get_textpage_ocr(language=settings.language, dpi=dpi, full=True,
                             tessdata=str(Path(settings.tessdata).resolve()))
    text = page.get_text(textpage=tp, sort=False)
    return dict(text=text, language=settings.language, requested_dpi=settings.dpi,
                effective_dpi=dpi, engine="pymupdf_tesseract", verification="not_verified")
