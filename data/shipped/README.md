# `data/shipped/` — the distilled payload a judge never has to build

The working corpus, `data/instances/arms/`, is **4.0 GB**: per instance it holds
the full `index.scip` (~67 MB, the pyright SCIP index) and the *complete* arm-A
and arm-B call graphs. None of that is needed to *run* the product. This
directory is the **17 MB** distillation `setup.sh` loads, so **no judge ever
re-indexes Django or re-parses a repo**. Real size on disk: **17,193,949 bytes
(~16.4 MiB)**, comfortably under the 50 MB ceiling.

## What ships vs. what is cut — say it plainly

This payload ships the **50 django instances** that back every demo, CLI example,
and video shot (`friction compare/list/check --issue django__django-…`, and the
`python -m friction.viz` figures). It does **not** ship the multi-repo fair-test
corpus, and cannot:

- The **fair-test corpus is 7 repos, 179 built / 172 usable** (django 44, sphinx
  44, matplotlib 33, xarray 21, pytest 19, requests 8, sympy 3). Its arm files
  live under `data/instances/corpus/` — **~500 MB, git-ignored** — because a full
  scip type-index of the scientific repos runs 12–18+ min/instance. That is a
  *regeneration input*, ten times the size of this whole payload; shipping it is
  neither possible under the 50 MB ceiling nor necessary to run the product.
- What ships **instead** is the corpus's committed *output*: `docs/corpus.md`
  (the per-repo census) and `docs/evaluation.md` (the leave-one-repo-out fair
  test — pooled held-out AUC, DeLong `p=0.046`, the confounds). `friction eval`
  and `friction connectivity` print those committed reports; they do not read the
  corpus arm files, so a clean clone reproduces the *reported numbers* without the
  500 MB behind them. This is the same cut as `docs/graph-delta.md`: report
  committed, regeneration inputs omitted.

So: **django (50) ships; the other six repos' 129 instances do not** — their
result is in `docs/`.

## What is here

| Path | Purpose |
| --- | --- |
| `arms/manifest.jsonl` | Per-instance/per-arm node+edge counts, id band, and `fix_site_ids`/`test_target_ids`. The cache `friction compare` / `list` read. **All 50 instances.** |
| `arms/path_stats.json` | The pinned live-engine answerability and bounded fix→test path counts per arm — the two-arm contrast `compare` renders. **All 50 instances.** |
| `arms/<instance_id>/nodes.ndjson.gz` | Both arms' bounded-neighbourhood `Function` nodes (band-disjoint), gzipped. |
| `arms/<instance_id>/edges.ndjson.gz` | Both arms' bounded-neighbourhood `CALLS` edges (band-disjoint), gzipped. |
| `annotations.json` | Per-instance fix-site and test-target function ids. |
| `resolved/*.json` | The three published SWE-bench ground-truth resolved-sets. |
| `manifest.json` | Machine-readable inventory of this directory. |

## The distillation: bounded neighbourhoods, both arms

`friction compare` / `list` / `delta` / `eval` are **cache-backed** — they read
only `arms/manifest.jsonl` + `arms/path_stats.json` + the `docs/` reports, never
a graph. So a clean clone can run the headline the moment the package is
installed; the engine is not even required for `compare`.

To *live-load* an arm and run one real `algo.MSpaths`, only the bounded
neighbourhood the query is defined over is needed. Every node that can lie on a
bounded fix→test path is within `maxLen` hops of an endpoint (see
`friction.subgraph`), so `scripts/distil_shipped.py` ships, per instance and per
arm, the induced **maxLen-6** neighbourhood of `fix_site_ids ∪ test_target_ids`,
capped at the engine's real envelope (`NODE_BUDGET = 16_000`,
`EDGE_BUDGET = 24_000`), in the arms' own disjoint id bands. If all 50 were
loaded that is **623,978 nodes / 1,186,841 edges**; `setup.sh` loads only a
small working set (below).

### Faithful for arm A; truncated for arm B — and that is the finding

`scripts/distil_shipped.py` reports: **arm A 0/50 truncated**, **arm B 47/50
truncated**. Arm A is sparse, so its maxLen-6 neighbourhood fits the budget and
is a faithful slice of the full arm — a live arm-A query returns the **same path
count** the cache recorded (verified: `django__django-10554` arm A returns 80
paths live, matching `path_stats.json`). Arm B is ~4× denser, so its maxLen-6
neighbourhood *exceeds* the 24k-edge budget and is truncated. This is the density
paradox in the data itself. Consequently:

- The faithful **live** demonstration is **arm A**.
- Arm B's full-graph unanswerability (24 of 28 comparable instances time out at
  maxLen 6, 1 OOMs) is the **cached** measurement in `path_stats.json`; it is
  *not* re-derivable from the shipped truncated arm-B slice, and `setup.sh` does
  not pretend otherwise.

## Scope / what is deliberately NOT shipped (so nothing looks complete when it isn't)

- **The per-instance `index.scip`** (~67 MB each) and the **full-arm graphs**
  beyond the maxLen-6 neighbourhood — regeneration inputs, rebuilt by
  `scripts/build_arms.py`.
- **The django checkout** (`data/repos/django`) and **`data/instances/ref_cache.json`**
  — needed only to reproduce the headline numbers via `friction.harness` /
  `scripts/graph_delta.py`, not to run the CLI.
- **`docs/graph-delta.md` regeneration inputs** (the repo + a ~67 MB `.scip`
  index). The report itself is committed under `docs/` and `friction delta`
  prints it; regenerating it needs the un-shipped repo + index.

All 50 instances are present in `arms/manifest.jsonl` and `arms/path_stats.json`,
so `friction compare --issue <any of 50>` works from the cache. Every instance's
bounded neighbourhood is shipped, so any instance can also be live-loaded via
`python -m friction.loader --dir <decompressed instance dir>`.

## Working-set safety (issue #81)

`setup.sh` loads a **small named working set** — `django__django-10554`,
`django__django-11087`, `django__django-10973` (both arms each, ~33k nodes / ~62k
edges combined) — a one-shot ingest of well under 1 GB of writes. That stays far
below the ~6.1 GB threshold at which the engine's `CLOUD_PROVIDER=local` SlateDB
`LocalFileSystem` backend hits its `PutMode::Update` defect (see the comment in
`docker-compose.yml` and `docs/engine-scaling.md`). Do **not** loop the loader
against a persistent `hydradb-data` volume, and do not bulk-load all 50 shipped
neighbourhoods into one persistent store.

## Engine pin

Built and loaded against HydraDB `02a40025d2d57e97ab2754c8256219cdbfeab379`
(v0.1.1, AGPL-3.0).

## The result this substrate produces (do not re-read as a positive)

The **headline** is the substrate finding: a name-matched call graph's edges have
a **precision ceiling of 0.746** against the type-resolved graph (Jaccard 0.3143)
— run `friction delta`. The secondary result is a **scoped, and now SIGNIFICANT,
NO-GO** on per-instance prediction: on the 7-repo fair test (**n=172**,
leave-one-repo-out) the directional features pool to a held-out AUC of **0.483**
(≤ chance) while `patch_lines` pools to **0.628**, and patch scope beats the
metric at **DeLong p=0.046** (bootstrap ΔAUC −0.089, 95% CI [−0.178, −0.003],
excludes zero) — run `friction eval`. Patch size wins, significantly; per-instance
prediction is *already solved* elsewhere at AUC 0.841 and is **not** claimed here.
Neither result is dressed up.
