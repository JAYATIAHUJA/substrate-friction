# `data/shipped/` — the pre-built graph a judge never has to build

`setup.sh` loads everything in this directory so **no judge ever runs
tree-sitter over Django**. The graph is committed as data; the engine is loaded
from it in one pass.

## What is here

| File | Purpose |
| --- | --- |
| `nodes.ndjson.gz` | Combined node rows for all 50 pre-built subgraphs (407,302 nodes). |
| `edges.ndjson.gz` | Combined edge rows for all 50 pre-built subgraphs (660,231 edges). |
| `subgraphs.json` | The manifest `friction check`/`friction list` read (fix/test endpoint ids, node/edge counts, band per instance). |
| `engine_cache.json` | Recorded engine answerability + cohort path/fan-in results; supplies the min-max bounds `friction check` normalises against, and the answered/timed-out/OOM status `friction list` prints. |
| `annotations.json` | Per-instance fix-site and test-target function ids. |
| `resolved/*.json` | The three published ground-truth resolved-sets (see Provenance). |
| `manifest.json` | Machine-readable inventory of this directory. |

`setup.sh` decompresses the two `.ndjson.gz` files in place, loads them into the
engine with `python -m friction.loader --dir data/shipped`, and copies
`subgraphs.json`, `engine_cache.json`, `annotations.json`, and `resolved/`
into `data/instances/` (which is `.gitignore`d and therefore absent on a clean
clone — the CLI reads them from there).

## Provenance

- **Dataset:** SWE-bench Verified, `django/django` instances. 231 django
  instances exist in the split; **50 are pre-built here**, of which **43 carry
  both a fix site and a test target** (the endpoint-bearing set the metric is
  scored on).
- **Base commits:** each subgraph is built at that instance's `base_commit`
  (recorded per instance in `subgraphs.json` under `base_commit`).
- **The `test_patch` WAS applied** before parsing. The graph reflects the repo
  tree at `base_commit` with the instance's gold `test_patch` applied, so the
  test targets the agent must reach actually exist as nodes. The solution patch
  is **not** applied — that is what the agent is being scored on.
- **Build path:** `friction.build` (tree-sitter Python) parses the tree into
  File/Class/Function nodes and CALLS/HAS_METHOD/INHERITS/IMPORTS edges;
  `friction.subgraph` slices each instance to the subgraph reachable within the
  traversal budget around its fix/test seeds and shifts every id into a disjoint
  band (`4_000_000_000 + i * 10_000_000`), so all 50 subgraphs coexist in one
  engine without id collisions.
- **Ground truth (`resolved/`):** three published SWE-bench systems —
  `20240402_sweagent_gpt4` (112/500), `20240620_sweagent_claude3.5sonnet`
  (168/500), and `20241029_OpenHands-CodeAct-2.1-sonnet` (265/500, the primary
  label). A `resolved` entry means that system's patch passed the instance's
  tests; the label is the outcome the friction metric is evaluated against.
- **Engine pin:** built and loaded against HydraDB
  `02a40025d2d57e97ab2754c8256219cdbfeab379` (v0.1.1, AGPL-3.0).

## Scope / what is deliberately NOT shipped

- **The full band-0 Django graph** (`data/graphs/django`, 46,565 nodes /
  190,061 edges) is not shipped. `friction check` addresses the **banded
  subgraph** ids (e.g. `4020005905`), so shipping the band-0 graph would not
  answer a single `check`. The subgraphs are the load target.
- **`ref_cache.json`** (the full reference path-enumeration cache used by the
  null/fidelity analysis) is not shipped; it is only needed to reproduce the
  headline numbers via `uv run python -m friction.harness`, not to run the gate.

## Working-set safety

The combined load is **407,302 nodes / 660,231 edges (~11.5 MB gzipped, 12 MB
total)** — a one-shot ingest of well under 1 GB of writes. That stays far below
the ~6.1 GB threshold at which the engine's `CLOUD_PROVIDER=local` SlateDB
LocalFileSystem backend hits its `PutMode::Update` defect (see the comment in
`docker-compose.yml` and the retraction in `docs/engine-scaling.md`). Do not
loop the loader against a persistent `hydradb-data` volume.

## The result this graph produces (do not re-read as a positive)

Scoring this substrate is a **NO-GO**: over the 43 endpoint-bearing instances the
friction metric does **not** predict agent failure — AUC 0.565, r=0.055,
p=0.726, a clean null. The confident-looking engine number (AUC 0.780) is a
demonstrated artifact of the engine's `pathCount = 20` truncation (fidelity
recall 0.0264). `friction eval` and `friction fidelity` print the full record.
