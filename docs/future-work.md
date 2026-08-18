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
- **LLM-driven abstention on SWE-bench:** the loop is demonstrated with a real
  MCP client and a disclosed scripted policy (`docs/abstention-demo.md`);
  wiring it into an LLM agent and measuring behaviour change at scale is the
  study that follows.
- **Upstream `RecallCert` PR:** drafted in `docs/upstream-issues.md`; opening
  it before the sketch genuinely builds would be theatre.
- **Live public deployment:** the blocker turned out to be our own missing
  secrets file, not the engine (see the #101 correction) — genuinely unblocked
  now, but a demo link stood up in the final hours would not meet the
  fail-closed bar this repo holds itself to.
- **LLM-assisted deep classification of `unique_unconfirmed` edges:** the
  deterministic taxonomy ships; per-edge root-causing (dynamic receiver vs
  decorator vs re-export) wants careful method disclosure and a bigger
  manual sample than the window allows.
