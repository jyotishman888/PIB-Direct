#!/usr/bin/env python3
"""
Stage 3 of the PYQ pipeline: tag parsed questions against your shared
vocabulary and emit importer-ready rows.

Usage
-----
    export ANTHROPIC_API_KEY=...
    python tag_pyq.py data/pyq/_raw_mains.json \
        --vocab data/pyq/vocabulary.txt \
        -o data/pyq/mains_2014_2023.json

    uv run pib-agent import-pyq data/pyq/mains_2014_2023.json

Writes two files:
  <out>.json         exactly {year, paper, question, syllabus_area} — import this
  <out>.review.csv   every row + confidence, sorted worst-first — read this

--vocab is a plain text file, one canonical term per line, exactly as the
shared vocabulary spells it. Anything the model returns that is not in that
file is rejected and forced into the review pile, so a hallucinated area can
never reach the importer.

Note that the confidence threshold only *flags*: a low-confidence row is still
written to the import file with whatever area was chosen. The review CSV is
the work queue, not a gate — work it before importing.

Re-running is safe: questions already present in <out>.json are skipped, so a
run that dies halfway costs you only the untagged remainder. The review CSV is
merged across runs rather than rewritten, so an earlier run's flags survive.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import defaultdict

BATCH = 10
DEFAULT_MODEL = "claude-sonnet-5"

SYSTEM = """You classify UPSC Civil Services examination questions against a \
fixed syllabus vocabulary.

You will be given a numbered list of questions. For each one, choose the single \
best-fitting area from the CONTROLLED VOCABULARY below.

CONTROLLED VOCABULARY (these are the only permitted values):
{vocab}

Rules:
- The "area" value must be copied character-for-character from the list above. \
Never invent, abbreviate, reword or merge entries.
- Judge what the question actually demands of the candidate, not the nouns it \
happens to mention. A question mentioning a river but demanding an answer about \
centre-state water disputes is a federalism question, not a geography one.
- "confidence" is your honest probability that a subject expert would agree with \
your choice: 0.9+ when the question sits squarely in one area, 0.5-0.7 when it \
straddles two, below 0.5 when nothing in the vocabulary fits well.
- Never inflate confidence to seem decisive. A low score is useful information; a \
wrong high score is not.

Respond with a JSON array and nothing else — no preamble, no markdown fences:
[{{"n": 1, "area": "<exact vocabulary string>", "confidence": 0.0}}]
One object per question, in the order given."""


def load_vocab(path: str, gs_paper: int | None = None) -> list[str]:
    with open(path, encoding="utf-8") as fh:
        terms = [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]
    if gs_paper is not None:
        scoped = [t for t in terms if re.search(rf"GS\s*Paper\s*{gs_paper}\b", t, re.I)]
        if scoped:  # only narrow if the vocabulary is actually paper-prefixed
            return scoped
    return terms


def make_batches(rows: list[dict], size: int) -> list[list[dict]]:
    """Split rows into batches that never span two GS papers.

    load_vocab narrows the vocabulary to one paper, and the batch is scoped by
    its *first* row — so a batch spanning two papers shows the model the wrong
    paper's terms for the rest, and the answer it gets back is still inside the
    vocabulary, which means the off-vocabulary guard cannot catch it. A mains
    paper has 20 questions and BATCH is 10, so batches divide exactly along
    paper boundaries and this stays invisible until one paper mis-parses by a
    single question; from there every later batch straddles.
    """
    by_paper: dict[object, list[dict]] = defaultdict(list)
    for row in rows:
        by_paper[row.get("gs_paper")].append(row)

    batches: list[list[dict]] = []
    for group in by_paper.values():  # insertion order: first appearance in the file
        batches += [group[i : i + size] for i in range(0, len(group), size)]
    return batches


def call_api(client, model: str, vocab: list[str], batch: list[dict]) -> list[dict]:
    listing = "\n".join(f"{i+1}. {r['question']}" for i, r in enumerate(batch))
    msg = client.messages.create(
        model=model,
        max_tokens=2000,
        system=SYSTEM.format(vocab="\n".join(f"- {v}" for v in vocab)),
        messages=[{"role": "user", "content": listing}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    return json.loads(text)


def load_existing_review(path: str) -> list[dict]:
    """Earlier runs' review rows, so a resume adds to the queue instead of wiping it."""
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:  # csv gives strings back; sorting needs the number
        try:
            row["confidence"] = float(row.get("confidence") or 0)
        except ValueError:
            row["confidence"] = 0.0
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("raw", help="output of parse_mains.py")
    ap.add_argument("--vocab", required=True, help="one canonical term per line")
    ap.add_argument("-o", "--out", required=True, help="importer-ready JSON path")
    ap.add_argument("--field", default="syllabus_area", choices=["syllabus_area", "topic"],
                    help="which field name the importer should see (default: syllabus_area)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--threshold", type=float, default=0.75,
                    help="rows below this land in the review file (default: 0.75)")
    ap.add_argument("--limit", type=int, help="tag only the first N — cheap smoke test")
    args = ap.parse_args()

    try:
        from anthropic import Anthropic
    except ImportError:
        sys.exit("uv pip install anthropic")
    client = Anthropic()

    with open(args.raw, encoding="utf-8") as fh:
        rows = json.load(fh)
    if args.limit:
        rows = rows[: args.limit]

    done: dict[tuple, dict] = {}
    if os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as fh:
            for r in json.load(fh):
                done[(r["year"], r["paper"], r["question"])] = r
        print(f"resuming — {len(done)} already tagged", file=sys.stderr)

    review_path = os.path.splitext(args.out)[0] + ".review.csv"
    review = load_existing_review(review_path)
    if review:
        print(f"carrying {len(review)} existing review row(s) forward", file=sys.stderr)
    seen_in_review = {r.get("question") for r in review}

    todo = [r for r in rows if (r["year"], r["paper"], r["question"]) not in done]
    tagged: list[dict] = list(done.values())
    batches = make_batches(todo, BATCH)
    processed = 0

    for batch in batches:
        vocab = load_vocab(args.vocab, batch[0].get("gs_paper"))
        allowed = set(vocab)

        results: list[dict] = []
        for attempt in range(3):
            try:
                results = call_api(client, args.model, vocab, batch)
                break
            except Exception as exc:                      # noqa: BLE001
                if attempt == 2:
                    sys.exit(f"batch at row {processed} failed three times: {exc}")
                print(f"  retry {attempt+1}: {exc}", file=sys.stderr)
                time.sleep(2 ** attempt)

        by_n = {r.get("n"): r for r in results}
        for j, row in enumerate(batch, start=1):
            res = by_n.get(j, {})
            area = res.get("area", "")
            conf = float(res.get("confidence", 0))
            rejected = ""
            if area not in allowed:                       # off-vocabulary → never imported
                rejected, area, conf = area, "", 0.0

            tagged.append({
                "year": row["year"],
                "paper": row["paper"],
                "question": row["question"],
                args.field: area,
            })
            # A re-tagged question replaces its earlier review row rather than
            # appearing twice.
            if row["question"] in seen_in_review:
                review = [r for r in review if r.get("question") != row["question"]]
            seen_in_review.add(row["question"])
            review.append({
                "confidence": round(conf, 2),
                "year": row["year"],
                "gs_paper": row.get("gs_paper", ""),
                "q_no": row.get("q_no", ""),
                args.field: area,
                "rejected_suggestion": rejected,
                "question": row["question"],
            })

        processed += len(batch)
        print(f"  tagged {processed}/{len(todo)} (GS{batch[0].get('gs_paper') or '?'})",
              file=sys.stderr)

        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:   # checkpoint every batch
            json.dump(tagged, fh, ensure_ascii=False, indent=2)

    if review:
        review.sort(key=lambda r: float(r["confidence"]))
        fields = ["confidence", "year", "gs_paper", "q_no", args.field,
                  "rejected_suggestion", "question"]
        with open(review_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(review)

    flagged = sum(1 for r in review if float(r["confidence"]) < args.threshold)
    print(f"\n{len(tagged)} rows -> {args.out}", file=sys.stderr)
    if not todo:
        print("nothing new to tag", file=sys.stderr)
    if review:
        print(f"{flagged} below {args.threshold} -> {review_path} (top of file)",
              file=sys.stderr)


if __name__ == "__main__":
    main()
