# FastAPI extraction coverage

`PENDING_GROUND_TRUTH_REVIEW`

The baseline uses the same saved pilot chunks and Gemini outputs. Provider calls for this evaluation total 0. Post-validation means the saved Markdown-aware replay.

| Measure | Count |
| --- | ---: |
| Chunks evaluated | 20 |
| Chunks with explicit or out-of-taxonomy annotations | 16 |
| Chunks with explicit in-taxonomy annotations | 14 |
| Explicit in-taxonomy relationship keys | 41 |
| Explicit out-of-taxonomy relationship annotations | 9 |
| Ambiguous relationship annotations | 5 |
| Unsupported relationship annotations | 5 |
| Entity annotations | 136 |
| Gemini raw relationship candidates | 8 |
| Accepted in the original live run | 1 |
| Accepted in the Markdown-aware replay | 2 |
| Evidence matches in the replay | 8 |
| Gemini raw entity rows | 67 |
| Retained entity rows from the live run | 63 |

Ground Truth counts, TP, FP, FN, precision, recall and F1 are pending independent review of the labels and all chunk inventories. The counts above include draft labels.

## Missing relationship audit

| Cause | Annotations |
| --- | ---: |
| `not_extracted` | 37 |
| `taxonomy_gap` | 9 |
| `validator_rejected_candidate` | 2 |

The saved artifacts preserve raw entity counts and retained entity objects. Raw entity precision and recall are unavailable. Retained entity scores use canonical names in chunks with approved entity labels.

See the [review guide](../README.md#extraction-coverage), [baseline source analysis](error_analysis.md), [candidate audit](extraction_comparison.json), and [missing relationship records](missing_relationships.jsonl).
