# Preserving the two independent manual reviews

This is a format guide, not review evidence or human approval. No example here establishes that a person performed a review or that an issue is correct.

Persons 1 and 4 independently review the revealed source policy for exactly 600 seconds before the first PolicyFuzz model attempt. Record observations contemporaneously in an external file while the frozen worktree remains clean. After the first run, import that original file byte for byte into the reviewer's owned evidence folder. Do not reformat, reconstruct, or edit the original when importing it.

The required pairs are:

| Owner | Imported original | Import wrapper |
| --- | --- | --- |
| Person 1 | `team/person-1-integration/evidence/manual-review.raw.json` | `team/person-1-integration/evidence/manual-review.json` |
| Person 4 | `team/person-4-evaluation/evidence/manual-review.raw.json` | `team/person-4-evaluation/evidence/manual-review.json` |

The raw file contains these fields:

| Field | Requirement |
| --- | --- |
| `reviewer_id` | Nonempty human identifier; the two identifiers must differ after NFC normalization, whitespace trimming, and case folding. |
| `reviewer_type` | `"human"`. |
| `independent` | Boolean `true`; actual independence remains a human responsibility. |
| `candidate_version` | Positive integer matching the active candidate. |
| `source_policy_sha256` | Exact source-byte digest from the active candidate. |
| `started_at`, `completed_at` | ISO 8601 timestamps with explicit timezone offsets. Their difference must be exactly 600 seconds. Completion must be no later than the current time and the blind attempt metadata's `started_at`. |
| `duration_seconds` | Integer `600`. |
| `reported_issues` | A list, including an empty list if nothing was reported. |
| `first_reported_issue_seconds` | Earliest issue observation time, or JSON `null` when the list is empty. |

Every reported issue contains `issue_id`, `description`, and `observed_at_seconds`. IDs are unique within that review and stable when later matched to gold. They begin with a letter or digit, use only letters, digits, `.`, `_`, `:`, or `-`, and contain at most 128 characters. Descriptions are nonempty. Observation times are integers from 0 through 600 inclusive; they record when the issue was reported, not a later judgment of correctness.

The wrapper copies these fields exactly from the original: `reviewer_id`, `reviewer_type`, `independent`, `candidate_version`, `source_policy_sha256`, `duration_seconds`, `started_at`, `completed_at`, and `first_reported_issue_seconds`. It adds:

- `external_file`: the exact repository-relative imported original path in the same owner's folder, as listed above.
- `external_file_sha256`: SHA-256 of the original file's exact bytes, including whitespace and final newline. This hashes the separate raw file, never the wrapper itself.

The wrapper does not replace the raw issue list. Preserve the external original and its imported bytes; only their matching byte hash establishes that the import is unchanged. Symlinks, path aliases, paths outside the repository, and another owner's original are refused.

Example structure only — placeholders below are intentionally not valid evidence and must never be imported as a completed review:

```text
Original manual-review.raw.json:
{
  "reviewer_id": <actual reviewer identifier>,
  "reviewer_type": "human",
  "independent": <actual human attestation>,
  "candidate_version": <active candidate integer>,
  "source_policy_sha256": <active source digest>,
  "started_at": <actual aware start timestamp>,
  "completed_at": <actual aware completion timestamp>,
  "duration_seconds": 600,
  "reported_issues": [
    {
      "issue_id": <stable local identifier>,
      "description": <original human observation>,
      "observed_at_seconds": <actual integer observation time>
    }
  ],
  "first_reported_issue_seconds": <minimum observation time, or null>
}

Wrapper manual-review.json:
{
  <the nine matching fields listed above>,
  "external_file": <exact owned manual-review.raw.json path>,
  "external_file_sha256": <SHA-256 of the original bytes>
}
```

`validate_manual_reviews(root, active, now=...)` returns the four wrapper/original relative paths for Gate B hashing, or raises `ManualReviewError`. `now`, when supplied for tests, must be a timezone-aware `datetime`. The validator reads the blind attempt's `team/person-1-integration/evidence/blind-first-run.json.metadata.json` to check ordering; Gate B separately binds that metadata.

The validator establishes structural consistency, not human identity, independence, observation truth, or correctness. Gold matching remains a separate assessment. Do not label `first_reported_issue_seconds` as time to first correct defect, and do not derive correct-defect counts from a reviewer's self-labels.
