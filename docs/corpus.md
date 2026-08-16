# Corpus (Task 4): multi-repo instance corpus

The evaluation corpus expanded from 50 django instances in a single repository to a multi-repo corpus, so a **leave-one-repo-out** split (Task 5) becomes possible and repo identity stops being a total confound.

Each instance is a SWE-bench Verified task built at its own `base_commit` with the test patch applied, indexed with scip-python, and emitted as two graph arms (name-matched A, type-resolved B) with fix-site and test-target endpoints resolved in each arm's id space. All builds ran against per-repo throwaway `git clone --shared` working trees; the reference clones under `data/repos/` were never checked out destructively.

**Usable n** = instances whose type-resolved arm B mapped **both** a fix site and a test target (an instance with no test endpoint cannot test a fix->test path). This is the number the evaluation can use; it is reported per repo, not just overall.

## Per-repo

| repo | attempted | built | usable n | mapping % | median nodes (B) | median edges (B) | wall (min) |
|---|--:|--:|--:|--:|--:|--:|--:|
| django | 50 | 50 | 44 | 88% | 28224 | 79446 | 99.2 |
| matplotlib | 34 | 33 | 33 | 100% | 11215 | 19317 | 150.4 |
| pytest | 19 | 19 | 19 | 100% | 5004 | 8169 | 5.7 |
| requests | 8 | 8 | 8 | 100% | 733 | 1555 | 1.0 |
| sphinx | 44 | 44 | 44 | 100% | 7289 | 19622 | 22.1 |
| sympy | 7 | 3 | 3 | 100% | 23660 | 78680 | 36.9 |
| xarray | 22 | 22 | 21 | 95% | 5108 | 19191 | 35.8 |
| **total** | | **179** | **172** | **96%** | | | |

**Total instances built: 179. Total usable n: 172.**

## Notes and honesty caveats

- **Repo selection deviated from the plan, on measured evidence.** The plan named the 3 largest non-django repos (real counts: sympy 75, sphinx 44, matplotlib 34 -- *not* scikit-learn as the plan guessed). sphinx and matplotlib built cleanly. **sympy, and the two next-largest candidates scikit-learn and astropy, index pathologically slowly** (~12-18+ min/instance for a full scip index of a large scientific codebase) -- scip index time scales with codebase size. Per the plan's own rule ('if a repo burns hours, stop and move to the next'), the corpus was filled out with the *smaller* SWE-bench repos, which index fast (requests ~7 s, pytest ~15 s, xarray ~2 min) and map endpoints at 100%. The result is a **7-repo** corpus -- broader than the planned 4, which is strictly better for leave-one-repo-out.
- **sympy was capped at 3** (throughput, not a mapping failure -- sympy's endpoints map at 100%). A concurrency finding: running two heavy scip indexers at once (sympy + matplotlib) OOM-crashes scip-python on sympy; run alone it succeeds. The builder now serialises heavy indexers. scikit-learn and astropy were cloned and piloted but dropped for the same throughput reason.
- **django (50) was carried, not rebuilt.** The existing `data/instances/arms/manifest.jsonl` records already carry the load-bearing endpoint fields (arm_b fix/test ids); rebuilding them would cost ~2.3 h and not change the usable-n figure. They are tagged `source: "carried"`. The newly built repos additionally carry the fuller typed node/edge census (`node_labels`/`edge_types`); the carried django records predate that field but are otherwise format-compatible on every field the evaluation reads.
- **Arm NDJSON location resolves by `source`.** Built records (`source: "built"`) store their arm files under `data/instances/corpus/arms/<id>/{arm_a,arm_b}/`; carried django records (`source: "carried"`) reuse the originals under `data/instances/arms/<id>/`. A consumer (Task 5) picks the base dir from the record's `source` field. Per-instance `index.scip` files are deleted after each build; the loader reads the NDJSON, not the SCIP.
- **django is the only repo below 100% mapping (88%, 44/50).** Its misses are inherited test methods with no physical def in the named subclass and module-level diff hunks (see `friction.arms` Finding 1). Every pytest-native repo maps at 95-100%, so the usable-n loss is concentrated in django, not spread across the corpus.
- **COVERS is static-only in this corpus.** Per-instance dynamic COVERS tracing (Task 1) is not folded into these arm files; each record is tagged `covers: "static-only"`. COVERS is unioned at analysis time by `friction.covers3` where a trace exists.
- **Power.** The project's power analysis needs ~610 instances to detect +0.05 AUC at rho=0.5; this corpus is still well short of that. What it buys is the ability to resolve *anything at all* (n=44 could not) and a repo-held-out split (Task 5).
