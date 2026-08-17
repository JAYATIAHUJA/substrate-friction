# Upstream issue drafts (file-ready)

Contributions to `hydra-db/hydradb` in the same register as issue #81 and
PR #82. Drafts only — filed when the user says go.

## Draft A — fresh-store bootstrap fails on ext4/overlay CI runners

**Title:** Fresh local store fails to bootstrap on Linux CI (`IsADirectory`)
while identical config bootstraps on macOS/Docker Desktop

**Body:** With `CLOUD_PROVIDER=local`, `LOCAL_PATH=/data/graph`, image
`ghcr.io/hydra-db/hydradb@sha256:db78309a…`, a fresh empty store bootstraps
cleanly on macOS/Docker Desktop but on a GitHub ubuntu-latest runner the node
starts, reaches placement state `fresh`, then exits:
`Error: Os { code: 21, kind: IsADirectory }`. Sequence observed while
narrowing: an absent `LOCAL_PATH` fails canonicalize (`NotFound`), a
pre-created `LOCAL_PATH` dir owned by uid 10001 reaches placement then dies
with `IsADirectory`. Repro workflow: `.github/workflows/hydra-verify.yml`
(`engine` job) in this repo — the failing runs are public. Expected: either
bootstrap from an empty dir (as on macOS) or a startup error naming the
missing prerequisite.

## Draft B — proposal: a `RecallCert` procedure

**Title:** Proposal: `algo.RecallCert` — certify a selection result against
labels, in-engine

**Body:** Motivating consumer: `friction gate` (this repo) measures whether a
graph-based test selection can reach labelled guarding tests; today the
verdict is computed client-side over per-edge traversals (2.0 ms each — see
`docs/engine-diff.md` for the reified anti-join pattern the dialect already
supports). A procedure taking `(sourceNodes, labelNodes, maxLen, threshold)`
and returning `{reached, total, recall, pass}` would make certification a
one-round-trip primitive and would let any selection tool built on HydraDB
ship a measured safety number instead of an assumed one. Sketch, semantics
and the label methodology are in this repo (`docs/gate.md`,
`docs/related-work.md`).
