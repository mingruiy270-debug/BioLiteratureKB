# Page-aware PDF reading with an explicit API budget

Use `biokb review-pdf` for a single paper or an authorized pilot before any bulk
digest refresh. It does not scan Zotero, alter the active prompt, calculate file
hashes, install OCR models, or start `sync`.

## What happens

1. Local native-text extraction keeps one labeled section per PDF page. A basic
   coverage TSV records sparse pages, visual candidates and parser warnings.
   Low extracted-text coverage retains the native alternative; no silent cut-off.
2. **Default is text and captions only (`--pages none`), one digest call.**
   Read the text first. Request an image only when it is scientifically important
   and contains necessary information the text/caption cannot explain. Image
   presence/complexity alone is not a reason to send it. `auto`
   uses sparse text, substantial raster images and body vector objects; this is a
   triage heuristic, not proof that unflagged pages contain no equations/tables.
   is offline candidate triage only, not permission to call vision. Inspect the
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

The local extractor also detects missing numbered equations/math glyphs and
retains the native alternative text. This avoids equating parser loss with
"not reported in the paper". It is a loss-warning heuristic, not a formula
correctness proof; important unresolved equations can justify a targeted image.

The legacy `sync`/`digest-prompt test` path remains text-only and does not inherit
these single-paper budget controls. Do not promise these limits for a library
sync. Use the bounded single-paper command for controlled pilots; separately
authorize any library-wide integration or refresh.

Official API references:
- https://api-docs.deepseek.com/guides/vision/
- https://api-docs.deepseek.com/guides/files_api/
- https://api-docs.deepseek.com/quick_start/pricing/
