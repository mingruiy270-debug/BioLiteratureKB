"""Local equation *candidates*, not a math OCR engine or correctness verifier."""
from __future__ import annotations

import math
import re


FORMULA_GUIDANCE = """
Formula evidence contract: native candidate blocks are fallible extraction, not
verified equations or LaTeX. For scientifically important equations preserve PDF
page/equation number, original expression, symbol definitions, reported dimensions,
units, index/reduction ranges, assumptions, constraints and role in the method.
Separate author expression from explanatory rewrite/derivation; do not silently
repair or algebraically simplify the source. Preserve sums versus means, weights,
subscripts/superscripts, minus signs, transpose, norm powers, log bases and domains.
When layout is unresolved, quote only visible fragments and leave the expression
unresolved: NEVER enumerate guessed alternative equations, including guesses said
to follow from dimensions. Symbol meanings require explicit source definitions;
a hat or conventional letter is not evidence of a visible definition. Separate
normalizing factors within terms from weights multiplying already-defined losses.
If a fraction denominator, bound or continuation is missing, do not write a
partial numerator as the formula definition. Use unresolved, not an equality.
Do not infer unit loss weights just from a missing coefficient or missing equation.
Use unclear/not_available_in_input for unresolved symbols/layout; extraction loss
is not evidence that the author omitted them. A crop verifies only its visible
region, never the whole page. Do not treat a rendered candidate as human-approved.
No formulas in a paper is legitimate: do not invent equations or fill empty cards.
"""


def validate_crops(value, maximum: int) -> list[dict]:
    """Explicit one-region-per-page requests in normalized displayed-page coords."""
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError("Formula crops must be a list within the visual-attempt limit")
    seen, result = set(), []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"page", "bbox", "reason"}:
            raise ValueError("Each formula crop needs exactly page, bbox, reason")
        page, box, reason = item["page"], item["bbox"], item["reason"]
        if type(page) is not int or page < 1 or page in seen:
            raise ValueError("Formula crop pages must be positive and unique")
        if (not isinstance(box, list) or len(box) != 4 or
                any(type(x) not in (int, float) or not math.isfinite(x) or not 0 <= x <= 1 for x in box) or
                box[0] >= box[2] or box[1] >= box[3]):
            raise ValueError("Crop bbox must be normalized [x0,y0,x1,y1] within 0..1, with positive area")
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
            raise ValueError("Give a nonempty reason (<=1000 chars) why text is insufficient")
        seen.add(page)
        result.append(dict(page=page, bbox=box, reason=reason.strip()))
    return sorted(result, key=lambda x: x["page"])


def preview_warnings(text: str, visual_notes: list[str]) -> list[dict]:
    """Conservative provenance triage, NOT mathematical or semantic validation.

    Warnings need source review; absence never certifies correctness. Equations
    without numbers are not covered. No additional API calls or rewriting.
    """
    warnings = []
    if not text.lstrip().startswith("---\n"):
        warnings.append(dict(kind="missing_digest_frontmatter", line=1,
                             action="Review metadata before KB ingestion; do not invent missing values"))
    pattern = r"(?:Eq(?:uation)?\.?\s*\(?|公式\s*[（(]?)([A-Za-z]?\d{1,3}[a-z]?)"
    supplied = set(re.findall(pattern, "\n".join(visual_notes), re.I))
    for i, line in enumerate(text.splitlines(), 1):
        if re.search(r"视觉转写|视觉核实|视觉恢复|visual(?:ly)?\s+(?:transcri\w*|verif\w*|recover\w*)", line, re.I):
            unsupported = set(re.findall(pattern, line, re.I)) - supplied
            if unsupported:
                warnings.append(dict(kind="visual_formula_attribution_needs_review", line=i,
                    equation_ids=sorted(unsupported), supplied_visual_equation_ids=sorted(supplied),
                    action="Check claim vs supplied notes; a warning is not proof of error, no warning is not proof of correctness"))
    return warnings


def equation_candidates(page, pdf_page: int) -> list[dict]:
    """Keep source blocks verbatim; candidates may include tables/inline math.

    Local context is geometric adjacency, NOT an asserted symbol-definition join.
    Raster/vector-only math can be absent. IDs identify candidates, not equations.
    """
    import pymupdf

    blocks = [b for b in page.get_text("blocks", sort=True) if len(b) >= 7 and b[6] == 0]
    result = []
    for i, block in enumerate(blocks):
        text = block[4]
        signals = []
        if re.search(r"[=∑∫⊙∈≤≥≈∝∂√]", text):
            signals.append("math_operator")
        if re.search(r"(?m)^\s*\((?:[A-Za-z]\.?\s*)?\d{1,3}[a-z]?\)\s*$", text):
            signals.append("standalone_equation_number")
        if not signals:
            continue
        # Text extraction coordinates are unrotated; crop coordinates are displayed.
        rect = pymupdf.Rect(block[:4]) * page.rotation_matrix
        rect &= page.rect
        w, h = page.rect.width, page.rect.height
        if rect.is_empty:
            continue
        neighbors = [blocks[j][4] for j in (i - 1, i + 1) if 0 <= j < len(blocks)]
        result.append(dict(
            candidate_id=f"p{pdf_page:03d}_candidate_{len(result)+1:03d}",
            pdf_page=pdf_page, equation_number_candidates=re.findall(r"\(((?:[A-Za-z]\.?\s*)?\d{1,3}[a-z]?)\)", text),
            bbox_normalized=[round(rect.x0/w, 6), round(rect.y0/h, 6), round(rect.x1/w, 6), round(rect.y1/h, 6)],
            native_expression_block=text, adjacent_native_context=neighbors,
            detection_signals=signals, expression_latex=None,
            recovery_status="native_candidate_unverified", manual_review_status="not_reviewed"))
    return result
