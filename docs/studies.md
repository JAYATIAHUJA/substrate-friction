# Pre-registered studies

Each study is registered here BEFORE its first full run. The result ships
whatever it is, nulls included. Numbers in these sections are filled in only by
the named script, never by hand.

## S1 — Corpus-scale gate audit (172 instances, 7 repos)

- **Registered:** 2026-08-18, before the first full-corpus run.
- **Hypothesis:** guarding-test recall on the full 7-repo corpus is in the same
  band as the django-only figure (arm_b 0.545); per-repo variation exists but
  no repo reaches the 0.95 skip bar.
- **Data:** `data/instances/corpus/` (129 non-django instances) +
  `data/instances/arms/` (50 django), endpoints from the committed manifests.
  Instances missing an endpoint set or a graph are excluded and counted, never
  scored.
- **Metric:** per-instance hit = selector returns ≥1 guarding test (k=6,
  predecessor walk). Recall = hits/n, per repo and pooled.
- **Analysis:** per-repo table + pooled, both arms; Wilson 95% interval on the
  pooled figure. No fitted parameters, so no train/test split; the pinned
  dev/sealed split is reported as a consistency check.
- **Script:** `scripts/gate_corpus.py` → `data/shipped/gate-results.json` →
  `docs/gate.md`.

## S2 — Audit the auditor (arm B vs dynamic ground truth)

- **Registered:** 2026-08-18, before computation.
- **Hypothesis:** arm B (SCIP/pyright) misses a nontrivial fraction of the
  test→fix connections that dynamic execution proves exist; the misses
  concentrate in framework-dispatch machinery (fixtures, `setUp`,
  parametrize).
- **Data:** the 18 traced django instances (`docs/covers.md` pipeline output),
  static arm_b connectivity vs static+COVERS connectivity, per instance.
- **Metric:** agreement table: connected(static) × connected(static+dynamic);
  arm B's miss rate against the dynamic-augmented reference on the traced
  subset.
- **Analysis:** 2×2 table + per-instance list of arm-B misses that dynamic
  evidence recovers. Small n (18) stated plainly; no significance claim.
- **Script:** `scripts/audit_auditor.py` → `docs/audit-the-auditor.md`.

## S3 — Wrong-edge taxonomy

- **Registered:** 2026-08-18, before classification.
- **Hypothesis:** unconfirmed name-matched edges concentrate in a small number
  of collision classes, with container/builtin method-name collisions
  (`extend`, `lower`, …) the largest class.
- **Data:** the 1,492 in-scope arm-A edges unconfirmed by arm B on django
  (`docs/graph-delta.md` pipeline).
- **Metric:** distribution over rule-based classes (assigned by deterministic
  rules on leaf name + target module; no LLM in the primary classification).
- **Analysis:** class distribution table + a random sample of 30 edges
  manually spot-checked, agreement rate reported.
- **Script:** `scripts/edge_taxonomy.py` → `docs/edge-taxonomy.md` +
  `data/shipped/taxonomy/`.

## S4 — Budget curves (recall vs identifier budget)

- **Registered:** 2026-08-18, before computation.
- **Hypothesis:** guarding-test recall degrades as the graph is truncated to
  its top-K PageRank identifiers, and the type-resolved arm degrades no slower
  than the name-matched arm.
- **Data:** shipped django instances, both arms.
- **Metric:** for K ∈ {25, 50, 100, 200, 400}: recall of the guarding test on
  the subgraph induced by the top-K PageRank nodes plus endpoint nodes'
  presence rule stated in the script.
- **Analysis:** recall(K) per arm; approximations (unweighted PageRank,
  induced-subgraph truncation) stated in the doc.
- **Script:** `scripts/budget_curves.py` → `docs/budget-curves.md`.

## S5 — The longitudinal ceiling (registered 2026-08-18, before any era was measured)

- **Hypothesis:** the name-match precision ceiling (0.746 at the pinned 2019
  commit) is not a constant of the technique but drifts as a codebase grows —
  we expect it to **decline** with repo age/size as name collisions accumulate.
- **Data:** django at release tags 1.11, 2.2, 3.2, 4.2, 5.0 (checked out from
  the existing clone's history); both arms rebuilt per era with the same
  extractors and the same identity join as `docs/graph-delta.md`.
- **Metric:** per era — compared edges, confirmed, unconfirmed, precision
  ceiling; plus arm sizes as covariates.
- **Analysis:** the five-point trajectory, reported as-is. A join that fails
  sanity (compared < 1,000 or zero intersection) is reported as `join_failed`
  for that era, never patched into a number.
- **Script:** `scripts/longitudinal.py` → `data/shipped/longitudinal.json` →
  `docs/longitudinal.md`.
