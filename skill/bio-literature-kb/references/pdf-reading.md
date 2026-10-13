# Page-aware PDF reading with an explicit API budget

Use `biokb review-pdf` for a single paper or an authorized pilot before any bulk
digest refresh. It does not scan Zotero, alter the active prompt, calculate file
hashes, install OCR models, or start `sync`.

## What happens

1. Local native-text extraction keeps one labeled section per in-scope PDF page. A basic
   coverage TSV records sparse pages, visual candidates and parser warnings.
   Low extracted-text coverage retains the native alternative; no silent cut-off.
2. **Default is text and captions only (`--pages none`), one digest call.**
   Read the text first. Request an image only when it is scientifically important
   and contains necessary information the text/caption cannot explain. Image
   presence/complexity alone is not a reason to send it. `auto`
   uses sparse text, substantial raster images and body vector objects; this is a
   triage heuristic, not proof that unflagged pages contain no equations/tables.
   It is offline candidate triage only, not permission to call vision. Inspect the
   text/plan and explicitly select 1-based `--pages 5,6` only when justified.
   Image-only/sparse pages receive a prose-transcription instruction, not a
   figure-only prompt. Unselected sparse pages or explicitly incomplete
   transcriptions stop the digest until OCR/reading scope is resolved.
3. One final call reads the complete extracted text plus bounded visual notes
   with the generic prompt. It explicitly lists visual pages not inspected.
   No second LLM call generates a JSON record in this workflow. Visual notes are
   limited in both output tokens and UTF-8 bytes; the final input reservation
   covers those bytes rather than assuming a fixed bytes-per-token ratio.

The API receives images, not PDF uploads. Native text is not the same as OCR, and
captions are not a substitute for examining figures. Dense/small labels may need
a separately reviewed crop/reading pass; do not invent values to fill gaps.

## Commands

```bash
# Offline plan: uses the existing local parser, no LLM/API call.
biokb review-pdf paper.pdf --root /path/to/kb --output reviews/paper-a \
  --version research_deepread_v2 --pages none

# Only after reviewing the scope/cost and obtaining authorization:
biokb review-pdf paper.pdf --root /path/to/kb --output reviews/paper-a \
  --version research_deepread_v2 --pages none --apply
```

The chosen prompt must exist in `<root>/prompts/`. The repository supplies
`research_deepread_v2`; installing a skill alone does not activate that version.

Default limits are at most **2 visual pages/attempts and USD 0.02 estimated visual
cost per paper**; normally no images are sent. The final report is allowed the
documented DeepSeek maximum, **393,216 output tokens (384K)**, with 800,000
conservatively reserved aggregate tokens and 5 total calls as safety ceilings.
There is **no default monetary cap on text** (`--max-usd 0`); it is an optional
whole-run cost gate, not a reason to shorten a deep-reading report. Max tokens
is a ceiling, not a target length or an advance charge. Each visual response is
capped at 1,536 tokens. Both calls
disable thinking in this extraction workflow: the pilot showed hidden reasoning
consuming the output budget and truncating the factual digest. Scientific
cross-paper reasoning is a separate task, not an automatic expensive step here.
These are configurable tradeoffs, not universal sufficient reading depths.

`--max-usd`, `--max-vision-usd`, `--digest-max-tokens`, `--max-calls`,
`--max-reserved-tokens`, `--max-vision-pages`, `--input-rate`, `--output-rate`
explicitly change the limits. Defaults for rates
are USD 0.30/M input and USD 1.20/M output, based on the DeepSeek Flash peak,
cache-miss rate checked 2026-10-13. Recheck rates and token/image accounting for
other dates/models/providers. This is an estimated application budget, not a
guarantee about the provider's invoice. Actual token usage is retained; unknown
usage or overruns stop further work rather than being concealed.

## Stopping and resuming

- Requests are sequential. The entire plan is checked before the first request;
  each request is also reserved and recorded **before** sending.
- Successful calls are reused when rerunning the exact same contract and intact
  outputs. A timeout, invalid usage, truncated response, or crash after send is
  not automatically retried: it may already have been billed.
- For a final digest with known usage and `finish_reason=length` only,
  `biokb complete-review reviews/paper-a --root /path/to/kb` previews one explicit
  text-only completion. `--apply` permits ONE additional request; earlier usage
  stays in the same cost/token ceiling, images are not resent, and unknown-use
  failures cannot use this recovery. This is not an automatic retry loop.
  Cached visual notes (including unresolved equations) are validated and reused
  with their original whole-page/crop scope; their text counts toward input cost.
- Input/prompt/limits/model changes stop resumption. Review them and use a new
  output directory only with new authorization for the additional expense.
- One transient `.running` process lock protects against concurrent duplication.
  Do not delete a stale lock until confirming its process has stopped.
- Reuse checks use path, size and mtime, not hashes. They protect normal workflow
  consistency, not adversarial tamper detection.

Outputs are a readable `source.md`, `coverage.tsv`, selected page JPEGs,
`visual_page_*.md`, `digest.preview.md`, and a single `review.json` containing the
plan, usage, statuses and restrictions. Do not publish paper files, base64
requests, generated digests, credentials or local paths to public repositories.

## Scientific quality check

Compare representative statements with the original page/Methods: names,
numbers, formulas, sample units, train/test design, figure relationships and
negative results. A successful API response or all-pages extraction is not proof
of accurate/full reading. Do not call previews official or claim parity with a
web UI without a matched quality comparison. Supplements and source code need
their own actual input; a prompt does not download them.

For a paid pilot, spot-check a small set of consequential main-paper claims before
handoff: especially comparator eligibility/ranking scope, statistical units,
normalization/loss definitions and negative results. Prompt strengthening alone
does not reliably fix such errors. Preserve raw API output; put source-supported
corrections in a clearly labeled reviewed copy, recording targeted review rather
than human approval or exhaustive verification. Keep only core unresolved issues,
not a task list of every missing supplement. No automatic paid rewrite loops.

The local extractor also detects missing numbered equations/math glyphs and
retains the native alternative text. This avoids equating parser loss with
"not reported in the paper". It is a loss-warning heuristic, not a formula
correctness proof; important unresolved equations can justify a targeted image.

The legacy `sync`/`digest-prompt test` path remains text-only and does not inherit
these single-paper budget controls. Do not promise these limits for a library
sync. Use the bounded single-paper command for controlled pilots; separately
authorize any library-wide integration or refresh.

## Formula recovery and targeted verification

Every local plan now writes `equations.json`: heuristic native-text candidate
blocks, PDF page, possible equation numbers, normalized bounding boxes and
adjacent native context. It is **not** complete mathematical OCR, validated
LaTeX, or a reliable symbol-definition join. Operators in prose/tables can be
false positives; raster/outlined or operator-free formulas may be missed.
Native LaTeX is left null rather than invented. Read `source.md` alongside it.

The digest records important equations in context: original expression, symbols,
reported dimensions/units, index/reduction ranges, assumptions, constraints,
implementation role and source location. Author expressions, explanatory
rewrites and uncertain recovery remain distinct. Do not force a formula table
on a paper without relevant mathematics. Missing extraction must never become
"the authors did not specify weights".

An actual DeepSeek test recovered the selected loss correctly but still guessed
another unresolved equation and misattributed it to visual evidence. Prompting
alone does not eliminate this risk. `review.json` therefore separates transport
completion from `semantic_review_status` and records `review_warnings` for missing
digest frontmatter and some numbered-equation visual-attribution mismatches.
These are conservative regex triage (false positives/negatives are possible),
not full metadata/schema or math validation. Agents must compare important
formula claims with their actual source before reuse/publication. Never infer
scientific approval from zero warnings or a successful API response.

If a critical equation remains unreadable, create a small JSON selection file:

```json
[
  {"page": 18, "bbox": [0.10, 0.35, 0.90, 0.65],
   "reason": "Loss subscripts and normalization denominator missing from native text"}
]
```

Coordinates refer to the **displayed PDF page**, origin top left; page is 1-based
and bbox is `[x0,y0,x1,y1]` normalized to 0..1. The numbers above are illustrative,
not a verified crop for a particular paper. Inspect local candidate geometry and
include the entire expression/number and nearby definitions, allowing padding.
One region per page; combine nearby equations if legible. Distant regions need
an explicitly reviewed subsequent pass, not automatic repeated requests.

```bash
biokb review-pdf paper.pdf --root /path/to/kb --output reviews/paper-a-formulas \
  --formula-crops formula-crops.json
# Inspect the offline plan and rendered pages/page_018.jpg before --apply.
```

`--formula-crops` and `--pages` selections are mutually exclusive. Selected crops
replace full-page images, consume the **same** visual-attempt/token/cost limits,
and get a math-transcription prompt (not the terse figure-caption prompt).
The crop is labeled as partial-page evidence in coverage and final input.
`formula_crops.json` retains the exact region/reason/native region text; it is
part of resume validation. Success is cached; failures are never auto-retried.
An unreadable formula is marked `UNRESOLVED_FORMULA`, remains a limitation in the
report and cannot be presented as a recovered fact. A crop cannot satisfy the
whole-page reading requirement of a sparse/scanned page: resolve OCR first.

Default remains one text call, no vision. No extra model call is made to build
the index or formula explanation; the latter is part of the final digest.
Contract version is now `bounded-review-9`; older prepared directories remain
untouched and cannot silently resume under changed extraction/prompt semantics.
This guard applies to `complete-review` too. Native formula candidate blocks
absent from Markdown are retained even when prose still mentions their number.

## Focus on the paper, not its bibliography

The generic prompt prioritizes the scientific question, essential methods, key
results and limitations. Do not summarize every reference or collect every
supplement. Expand only material needed to understand a central claim. This is
not permission to omit inconvenient negative findings or essential Methods.

After inspecting the document layout, `--text-pages 1-12,15-20` explicitly selects
the relevant pages (example only). Do not simply stop at the first References:
some journals place Methods afterward. The CLI defaults to `all` rather than
guessing section boundaries; the agent chooses a smaller scope when justified.
Mixed body/reference pages may be kept, while the prompt ignores unrelated
bibliographic listings. Page selection preserves original PDF numbering, records
excluded pages in coverage/plan and forbids selecting images outside that scope.
Excluded pages are not "read", not "missing", and not a whole-PDF reading claim.
Changing scope requires a new output directory; no stale paid result is reused.

## Optional local OCR, only for needed sparse pages

```bash
biokb review-pdf paper.pdf --root /path/to/kb --output reviews/scanned-main \
  --text-pages 1-10 --ocr-sparse --ocr-tessdata /path/to/tessdata \
  --ocr-language eng --ocr-dpi 300
```

Install compatible local Tesseract language data separately. This command does
not download/install anything or use a paid OCR API. PyMuPDF's integrated OCR
needs a compatible runtime and traineddata; the tested local wheel could use
explicit traineddata without a separately installed Tesseract executable.
Other builds may require the application as described in the official docs.

Only in-scope pages with <200 native characters are OCR candidates. Rendering is
bounded at 20 million pixels per page; no GPU model is loaded. `ocr_pages.json`
records recognized text, language, effective DPI, runtime version and local model
path/size/mtime. Prepared OCR is cached through normal resume checks. Too-short
OCR still blocks reading; longer OCR is labeled unverified, **not** proven good.
Checkbox state, dense forms, mathematical layout and numbers remain fallible.
Do not infer selected form choices from OCR text. OCR failure does not silently
trigger paid vision. Unrelated scanned appendices may instead be explicitly
excluded; do not spend effort recognizing them merely to claim exhaustive scope.

Sources: [PyMuPDF OCR](https://pymupdf.readthedocs.io/en/latest/recipes-ocr.html),
[Tesseract fast language data](https://github.com/tesseract-ocr/tessdata_fast).

Official API references:
- https://api-docs.deepseek.com/guides/vision/
- https://api-docs.deepseek.com/guides/files_api/
- https://api-docs.deepseek.com/quick_start/pricing/
