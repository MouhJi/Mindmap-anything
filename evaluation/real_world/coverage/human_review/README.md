# FastAPI Ground Truth review

**Status:** `PENDING_GROUND_TRUTH_REVIEW`

| Inventory | Count |
| --- | ---: |
| Pilot chunks and corresponding checklist rows | 20 |
| Total entity and relationship annotations | 196 |
| Entity annotations in the original draft | 136 |
| Relationships requiring human review | 60 |
| Explicit in-taxonomy drafts | 41 |
| Ambiguous drafts | 5 |
| Unsupported examples | 5 |
| Potential taxonomy gaps | 9 |
| Chunks with zero relationship rows | 0 |
| Chunks with zero explicit in-taxonomy drafts | 6 |
| Chunks with neither an explicit draft nor a taxonomy-gap draft | 4 |

The six chunks without an explicit in-taxonomy draft are dataset lines
13, 18, 43, 65, 83 and 87. Lines 83 and 87 contain potential taxonomy gaps.
The other four contain ambiguous or unsupported examples only. All 20
inventories need a completeness check before any of those chunks can be
confirmed as having zero in-scope relationships. [Chunk checklist](chunk_checklist.csv)

## Dataset integrity

The annotations are aligned with the 20 chunks identified by the saved
`gemini-3.5-flash-lite` pilot.

| Check | Result |
| --- | --- |
| Original review CSV against draft JSONL | All 216 rows agree on IDs, source URLs, dataset lines, and hashes. The 196 evidence-bearing rows also agree on their original quotes, and both status fields are pending on all rows. |
| Chunk text and identifiers against the original export | All 89 parsed records equal the Git export from commit `180f8b503b1dce3c19be6b7b08243b3f89b04758`. The 20 selected IDs, exact text, document IDs and source URLs agree with that export. |
| Chunk reconstruction from the six saved FastAPI pages | All 20 selected chunks were reproduced in memory with identical text, chunk IDs, document IDs, URLs, heading paths and content hashes. |
| Successful pilot records | All 20 agree on chunk ID, dataset line, project and document IDs, URL, title, heading path and recomputed content hash. Each has a unique corresponding saved cache outcome by completion time, metrics and candidate counts. |
| Source evidence | All 196 draft evidence strings are verbatim substrings of their selected chunks. All 8 replay evidence spans match the exact source characters at their saved offsets. |

The previously reported per-chunk mismatch could not be reproduced with the
available artifacts. Two comparisons do produce different digests:

- **Whole JSONL file checksum.** The Windows checkout has 89 CRLF record
  endings. The Git blob uses LF. Replacing only those record delimiters makes
  the files byte-identical. The parsed source strings are identical before and
  after this comparison.
- **Raw-text SHA-256.** All 20 raw-text digests differ from `content_hash`.
  The pipeline hashes the compact UTF-8 JSON array
  `[document_id, url, text, topic]` with SHA-256 and prefixes it with
  `chunk_`. The separate `chunk_id` hashes a different tuple that includes
  source offsets and chunking settings.

The historical mismatch inputs were unavailable, so their specific cause is
unconfirmed. The saved Gemini artifacts identify the requests by provenance
and cache outcomes. They contain no separate full-text request transcript.
[Original chunk export](../../chunking_results/chunks.jsonl) ·
[Original annotation CSV](../ground_truth_review.csv) ·
[Saved candidate audit](../extraction_comparison.json)

## Review in Excel

1. Copy [relationship_review.csv](relationship_review.csv) and
   [chunk_checklist.csv](chunk_checklist.csv) to a working folder. The files use
   UTF-8 with a BOM, comma delimiters and quoted multiline fields. If needed,
   import via **Data → From Text/CSV** and select **UTF-8**, **Comma** and no
   automatic data type detection. Turn on **Wrap Text** or use the formula
   bar to read the full Markdown in long context cells.
2. Review each relationship's exact quote in the full chunk. Verify the
   subject, object, direction, predicate, negation, and scope. Update
   `review_status` and `reviewer_notes`. The draft's `proposed_label` and
   `annotation_status` record the original classification and status.

| Decision | When to use it |
| --- | --- |
| `approved` | The exact source supports the directed relationship with an existing taxonomy type. An ambiguous draft may be approved after the reviewer resolves the uncertainty from the same chunk. |
| `rejected` | The source contradicts the claim, supplies only an example or mention, or supports a different relationship. Use this for confirmed unsupported examples. |
| `ambiguous` | The reviewer finds that the source leaves direction, scope, or meaning uncertain. Record the uncertainty in the notes. |
| `needs_taxonomy_change` | The source supports the relationship and the existing taxonomy lacks a precise type. Record the proposed type and rationale in `reviewer_notes` if the draft does not already include them. |

3. Work through every checklist row. Filter relationships by `dataset_line`
   or `chunk_id`, then read the complete source context and follow the
   chunk-specific omission check. Record whether the review found additions,
   including explicit zero findings. Set `inventory_status` to `reviewed`
   and enter your name in `reviewer` when the inventory is complete.
4. Append a row to the relationship CSV for each newly found edge or
   correction. Assign a unique ID such as `H-26-01`. Copy the exact
   `chunk_id` from the checklist and fill in `source_entity`,
   `relationship_type`, `target_entity`, `exact_source_evidence`,
   `review_status`, and `reviewer_notes`. For a taxonomy gap, use
   `needs_taxonomy_change` and fill `proposed_relationship_type`.
   Leave source metadata blank or copy it from the matching checklist row.
   Use notes to reference a corrected draft's original ID and resolve that
   original row separately.
5. Save both working files as **CSV UTF-8 (Comma delimited)**. From the
   repository root, finalize the reviewed copy with the command below. The
   export requires all 60 original relationship decisions and all 20
   named inventory reviews. It validates exact evidence and preserves
   source IDs and hashes. It exports only approved in-taxonomy
   relationships and refuses approval of the original unsupported or
   taxonomy-gap drafts.

```powershell
python -B -m evaluation.real_world.prepare_ground_truth_review --finalize --review-dir PATH_TO_WORKING_FOLDER
```

The output `approved_relationships.jsonl` is the reviewed relationship
dataset. Entity decisions can be recorded in a copy of the
[original combined CSV](../ground_truth_review.csv). This workflow produces
no precision or recall metrics.

To generate a fresh set of blank review sheets, run
`python -B -m evaluation.real_world.prepare_ground_truth_review --review-dir NEW_FOLDER`.
Both commands read the original local pilot artifacts described in the
[evaluation guide](../../README.md#extraction-coverage).

## Potential taxonomy gaps

| Proposed type | Drafts | Check during review |
| --- | --- | --- |
| `DEFAULT_ENDPOINT` | L40-R03, L58-R03, L60-R04 | Confirm the normal/default route and distinguish explicitly configured alternatives. |
| `COMPATIBLE_WITH` | L02-R07, L02-R09 | Confirm compatibility with each named standard separately from the existing `BASED_ON` claim. |
| `RUNS_IN` | L86-R02, L87-R01 | Confirm the documented execution context for functions declared with plain `def`. |
| `MUTUALLY_EXCLUSIVE_WITH` | L33-R03 | Confirm the exclusion applies to the two nested fields in `license_info`. |
| `RETURNS` | L83-R01 | Confirm the return contract for an `async def` function. |
