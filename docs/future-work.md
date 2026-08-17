# Future work (locked scope — one honest sentence each)

- **Full bitemporal longitudinal study (0.746 ceiling at every django major,
  2015→2026):** needs sentinel-interval edges and per-era indexing far beyond
  the submission window.
- **In-engine consensus graph server at production scale:** the cached
  certified graph ships (`docs/certified-graph.md`); serving live multi-arm
  consensus needs ingestion throughput work first.
- **Language #2 (Java via SWE-bench-java + scip-java):** the oracle and
  pipeline port, the corpus build does not fit the window.
- **Field trial (the gate in a real repo's CI for weeks):** requires calendar
  time no hackathon has.
- **Upstream `RecallCert` PR:** drafted in `docs/upstream-issues.md`; opening
  it before the sketch genuinely builds would be theatre.
- **Self-gating GitHub Action on our own PRs:** needs an exclude-path option
  in `gate --repo` (this repo vendors 9 corpus repos that must not be parsed);
  small, but not smaller than the honesty bar for shipping it untested.
- **Live public deployment:** killed without hesitation per the fresh-store
  bootstrap bug on runner-class filesystems (upstream Draft A) — the repo must
  not ship a dead demo link.
- **LLM-assisted deep classification of `unique_unconfirmed` edges:** the
  deterministic taxonomy ships; per-edge root-causing (dynamic receiver vs
  decorator vs re-export) wants careful method disclosure and a bigger
  manual sample than the window allows.
