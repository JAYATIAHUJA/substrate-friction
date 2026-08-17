# Reuse policy

This project studies other code-graph tools and cites their published results.
It copies none of their code.

| Project | Licence | Used how |
|---|---|---|
| `repowise-dev/repowise` | AGPL-3.0 | Cited only. Published benchmark figures and source-visible facts (the asserted tier confidences) are quoted with attribution. No code copied or vendored. |
| `repowise-dev/repowise-bench` | none — all rights reserved | Not used. Absence of a licence means absence of permission. |
| `hydra-db/hydradb` | AGPL-3.0 | Used as a running service over Bolt. Not linked against. Two findings contributed back: issue #81, PR #82. |

Methods and conventions are not code, and several here are adopted openly from
the better-run projects in this field: pinning a holdout split before measuring,
publishing the results that lose, stating how to read a number, and designing
agent-facing tools to accept several targets per call. Those are credited where
they appear (`docs/related-work.md`).

Everything in `src/` was written for this project inside the hackathon window
that opened 2026-08-12.
