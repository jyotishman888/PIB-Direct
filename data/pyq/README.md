# Past-year questions

Real questions from previous UPSC papers. Once imported, they surface on any
article whose syllabus areas they share (see `src/pib_agent/pyq/matching.py`),
turning "worth studying" from an opinion into evidence: *this area was examined
in 2023 and 2019*.

Nothing in this project generates these. A fabricated "this was asked in 2019"
is the fastest way to lose an aspirant's trust, so the corpus is fed only by
import, and every row records its `source` — which is what makes a bad batch
identifiable and removable later.

## Getting the questions

**UPSC's own PDFs are scans.** All 44 papers checked in September 2026 had zero
embedded fonts and no text layer, so `pdftotext`, `pdfplumber` and
`scripts/parse_mains.py` all read nothing from them. They need OCR, and these
are bilingual two-column scans — the layout OCR handles worst.

The cheaper route is to collect the text from a site that publishes mains
questions as text (InsightsOnIndia, Drishti and similar), straight into
`template.csv`. Ten years of GS2 + GS3 is roughly 400 questions. GS1 and GS4
barely intersect with press releases, so start with 2 and 3.

Fill in `year`, `paper` (`mains`), `gs_paper` and `question`. Leave
`syllabus_area` blank — stage 3 fills it in — or paste the source's own label
into `topic` and the importer will normalise that instead.

```bash
# 3. Tag each question with a syllabus area. Accepts your CSV directly.
python scripts/tag_pyq.py data/pyq/mains.csv \
    --vocab data/pyq/vocabulary.txt \
    -o data/pyq/mains_2014_2023.json

# 4. Load it. Idempotent — re-running a file changes nothing.
uv run pib-agent import-pyq data/pyq/mains_2014_2023.json \
    --source "UPSC mains GS2+GS3 2014-2023"
```

If you already have the areas filled in, skip stage 3 and import the CSV
directly — `import-pyq` reads CSV as readily as JSON.

## From text-layer PDFs

If you find papers that *do* carry a text layer, `scripts/parse_mains.py`
turns them into stage 3's input. Put them in `data/pdfs/`, then:

```bash
# 2. PDFs -> structured rows. Deterministic, no model calls.
#    Run with --inspect first; the checksums catch a mangled parse.
python scripts/parse_mains.py data/pdfs/*.pdf --inspect
python scripts/parse_mains.py data/pdfs/*.pdf -o data/pyq/_raw_mains.json

# 3. Tag each question with a syllabus area. Costs a few cents.
#    Writes an importer-ready JSON plus a .review.csv sorted worst-first.
python scripts/tag_pyq.py data/pyq/_raw_mains.json \
    --vocab data/pyq/vocabulary.txt \
    -o data/pyq/mains_2014_2023.json

# 4. Load it. Idempotent — re-running a file changes nothing.
uv run pib-agent import-pyq data/pyq/mains_2014_2023.json \
    --source "UPSC mains GS2+GS3 2014-2023"
```

Read `data/pyq/mains_2014_2023.review.csv` before step 4. The confidence
threshold only *flags*: a low-confidence row is still written to the import
file with whatever area was chosen, so the review file is a work queue rather
than a gate.

## vocabulary.txt

Generated from `src/pib_agent/syllabus.py`, and guarded by
`tests/test_pyq_vocabulary.py` — a stale copy would make `tag_pyq.py` reject
correct areas, since it treats anything outside the file as a hallucination.
After changing `GS_AREAS`, regenerate it:

```bash
uv run python -c "from pathlib import Path; from pib_agent.syllabus import GS_AREAS; \
p = Path('data/pyq/vocabulary.txt'); \
head = ''.join(l + '\n' for l in p.read_text(encoding='utf-8').splitlines() if l.startswith('#')); \
p.write_text(head + '\n'.join(GS_AREAS) + '\n', encoding='utf-8')"
```

## Format

If you already have questions in another form, skip stages 2-3 and import
directly. CSV or JSON with these fields:

| field           | required | notes |
|-----------------|----------|-------|
| `year`          | yes      | integer, e.g. `2019` |
| `paper`         | yes      | `prelims` or `mains` |
| `question`      | yes      | the question text |
| `syllabus_area` | no       | a canonical GS area (see `vocabulary.txt`) |
| `topic`         | no       | the source's own topic label, kept verbatim |

No answer field, by design. Matching only needs `(year, paper, syllabus_area)`
— the corpus is a signal of what gets examined, not a question bank, and a
wrong answer key imported at scale would be actively harmful.

`syllabus_area` and `topic` are both normalised onto the same closed vocabulary
the articles use, which is what turns matching into a join on a shared taxonomy
rather than fuzzy text overlap. Anything that doesn't map confidently is stored
as NULL rather than guessed at: a wrong area would surface an unrelated
question against an article, which is worse than showing none.

Import is idempotent — duplicates are detected on `(year, paper, question)`, so
re-running a file after a partial failure changes nothing.

## Example

```csv
year,paper,question,syllabus_area,topic
2019,prelims,"Consider the following statements regarding X:",GS Paper 3 - Environment and Biodiversity,Environment
2022,mains,"Discuss the challenges of Y in India.",,Science & Technology
```
