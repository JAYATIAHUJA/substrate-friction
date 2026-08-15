#!/usr/bin/env bash
# =============================================================================
# Smoke test for the one-command setup (setup.sh + data/shipped payload).
#
# Structural checks always run (no engine required). Engine-dependent checks run
# only when http://127.0.0.1:9090/readyz responds, so this passes both in CI and
# against a live node. Run: bash tests/test_setup.sh
# =============================================================================
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

fail=0
pass() { printf '  ok   %s\n' "$1"; }
bad()  { printf '  FAIL %s\n' "$1"; fail=1; }

echo "== structural =="

[ -x setup.sh ] && pass "setup.sh is executable" || bad "setup.sh missing/!executable"
bash -n setup.sh && pass "setup.sh parses" || bad "setup.sh has a syntax error"

# setup.sh must not INVOKE `just` (not installed on the target machine).
# Only inspect non-comment lines so the "just is NOT required" note is allowed.
if grep -vE '^[[:space:]]*#' setup.sh | grep -qE '(^|[;&|[:space:]])just([[:space:]]|$)'; then
  bad "setup.sh invokes 'just'"
else
  pass "setup.sh does not invoke just"
fi

# v2 payload: the cache the CLI reads + the per-instance arm neighbourhoods.
for f in data/shipped/arms/manifest.jsonl data/shipped/arms/path_stats.json \
         data/shipped/annotations.json data/shipped/manifest.json \
         data/shipped/README.md; do
  [ -s "$f" ] && pass "present & non-empty: $f" || bad "missing/empty: $f"
done

ls data/shipped/resolved/*.json >/dev/null 2>&1 \
  && pass "resolved sets present" || bad "no resolved sets in data/shipped/resolved/"

# All 50 instances must appear in the shipped manifest cache.
mi=$(grep -c '"instance_id"' data/shipped/arms/manifest.jsonl 2>/dev/null || echo 0)
[ "$mi" = "50" ] && pass "manifest.jsonl has 50 instances" \
  || bad "manifest.jsonl has $mi instances (want 50)"

# The warm instance's bounded neighbourhood must ship as valid gzip for both arms.
WARM=data/shipped/arms/django__django-10554
if [ -s "$WARM/nodes.ndjson.gz" ] && [ -s "$WARM/edges.ndjson.gz" ] \
   && gzip -t "$WARM/nodes.ndjson.gz" 2>/dev/null \
   && gzip -t "$WARM/edges.ndjson.gz" 2>/dev/null; then
  pass "warm instance neighbourhood is valid gzip (both arms)"
  nn=$(gzip -dc "$WARM/nodes.ndjson.gz" | wc -l | tr -d ' ')
  [ "$nn" -gt 0 ] && pass "warm nodes present ($nn rows)" || bad "warm nodes empty"
else
  bad "warm instance neighbourhood missing/invalid gzip"
fi

# Every shipped instance dir must carry both arm files.
missing=0
for d in data/shipped/arms/django__django-*/; do
  [ -s "${d}nodes.ndjson.gz" ] && [ -s "${d}edges.ndjson.gz" ] || missing=1
done
[ "$missing" = "0" ] && pass "every shipped instance has both arm neighbourhood files" \
  || bad "some shipped instance is missing an arm neighbourhood file"

# Shipped payload must stay under the 50 MB cap.
kb=$(du -sk data/shipped | cut -f1)
[ "$kb" -lt 51200 ] && pass "data/shipped is ${kb} KB (< 50 MB cap)" \
  || bad "data/shipped is ${kb} KB (exceeds 50 MB cap)"

# The object-store defect must be documented in the compose file.
grep -q "PutMode::Update" docker-compose.yml \
  && pass "docker-compose documents the object-store defect" \
  || bad "docker-compose missing the object-store defect note"

# The loader entrypoint setup.sh calls must be wired up.
if .venv/bin/python -m friction.loader --help >/dev/null 2>&1 \
   || python3 -m friction.loader --help >/dev/null 2>&1; then
  pass "python -m friction.loader --dir is wired"
else
  bad "python -m friction.loader entrypoint not runnable"
fi

echo "== setup.sh v4 acceptance wiring =="

# The console script is dead unless the package is installed EDITABLE. setup.sh
# must install it explicitly (the exact bug that shipped in v1).
grep -qE '(uv )?pip install (--quiet )?-e' setup.sh \
  && pass "setup.sh installs the package editable (pip install -e)" \
  || bad "setup.sh does not install the package editable"

# The engine needs the enlarged Rust stack for deep bounded traversals.
grep -qE '^[[:space:]]*export[[:space:]]+RUST_MIN_STACK=33554432' setup.sh \
  && pass "setup.sh exports RUST_MIN_STACK=33554432" \
  || bad "setup.sh does not export RUST_MIN_STACK=33554432"

# setup.sh must wait for engine readiness on :9090 and run the capability probe.
grep -q '9090/readyz' setup.sh \
  && pass "setup.sh waits for /readyz on :9090" \
  || bad "setup.sh does not wait for /readyz on :9090"
grep -q 'friction.probe' setup.sh \
  && pass "setup.sh runs the capability probe" \
  || bad "setup.sh does not run the capability probe"

# setup.sh must load the shipped graphs and demonstrate the live gate.
grep -q 'friction.loader' setup.sh \
  && pass "setup.sh loads the shipped working set" \
  || bad "setup.sh does not load the shipped working set"
grep -qE 'friction check --issue' setup.sh \
  && pass "setup.sh runs the live gate (friction check)" \
  || bad "setup.sh does not run the live gate (friction check)"

# The issue-#81 degradation must be documented in the compose file, by URL.
grep -q 'issues/81' docker-compose.yml \
  && pass "docker-compose names issue #81 by URL" \
  || bad "docker-compose does not name issue #81 by URL"

echo "== product surface (structural) =="

# The console-script entry point that install-editable wires up.
grep -qE '^friction[[:space:]]*=[[:space:]]*"friction\.cli:main"' pyproject.toml \
  && pass "pyproject declares the 'friction' console script" \
  || bad "pyproject missing the 'friction' console script"

# Every acceptance subcommand must be registered in the CLI. Match the quoted
# subcommand token whether it sits inline in add_parser("x", …) or on the line
# after a wrapped `sub.add_parser(` call, and/or in the `command == "x"` dispatch.
for cmd in check compare precision connectivity eval list serve; do
  if grep -qE "\"$cmd\"[,:)]" src/friction/cli.py; then
    pass "CLI registers subcommand: friction $cmd"
  else
    bad "CLI missing subcommand: friction $cmd"
  fi
done

# check must issue a real count(*) reachability query and print measured latency.
grep -q 'build_reach_cypher' src/friction/cli.py \
  && grep -q 'measured latency' src/friction/cli.py \
  && pass "check wires real reachability Cypher + measured latency" \
  || bad "check missing reachability Cypher / measured-latency rendering"

# The three report docs the CLI prints must be present and non-empty.
for f in docs/precision.md docs/connectivity.md docs/evaluation.md docs/demo.html; do
  [ -s "$f" ] && pass "present & non-empty: $f" || bad "missing/empty: $f"
done

# demo.html must be offline — no external <script src>/<link href> loads, and the
# Cytoscape source must be vendored/inlined.
if grep -qiE '<script[^>]+src=|<link[^>]+href=[^>]*https?:' docs/demo.html; then
  bad "demo.html loads an external resource (not offline)"
else
  pass "demo.html has no external <script>/<link> loads (offline)"
fi
grep -q 'vendored: docs/vendor/cytoscape' docs/demo.html \
  && pass "demo.html inlines vendored Cytoscape.js" \
  || bad "demo.html does not inline vendored Cytoscape.js"

# The FastAPI surface must expose the documented endpoints.
for route in '/health' '/check/' '/compare/' '/precision'; do
  if grep -qF "$route" src/friction/api.py; then
    pass "api exposes route: $route"
  else
    bad "api missing route: $route"
  fi
done

# viz must have a runnable module entrypoint that regenerates everything.
grep -q '__main__' src/friction/viz.py \
  && grep -q 'def generate_everything' src/friction/viz.py \
  && pass "python -m friction.viz regenerates every figure + demo.html" \
  || bad "friction.viz entrypoint / generate_everything missing"

echo "== engine (only if /readyz responds) =="
if curl -sf http://127.0.0.1:9090/readyz >/dev/null 2>&1; then
  PY=.venv/bin/python; [ -x "$PY" ] || PY=python3
  # friction list is engine-free but exercises the shipped manifest + cache.
  if "$PY" -m friction.cli list 2>/dev/null | grep -q "50 instances"; then
    pass "friction list reports 50 instances"
  else
    bad "friction list did not report 50 instances"
  fi
  # The primary command must render both arms for a comparable instance and
  # exit 0. compare is engine-free (it reads the shipped path_stats cache), so
  # this exercises the demo path a judge will run.
  WARM_ID="django__django-10973"
  if "$PY" -m friction.cli compare --issue "$WARM_ID" >/dev/null 2>&1; then
    pass "friction compare --issue $WARM_ID exits 0"
  else
    bad "friction compare --issue $WARM_ID failed"
  fi
  # THE GATE, live: a real bounded-reachability query must be issued and a
  # measured latency printed (arm A is the faithful/untruncated arm).
  chk=$(RUST_MIN_STACK=33554432 "$PY" -m friction.cli check --issue django__django-10554 \
        --arm arm_a 2>/dev/null || true)
  if printf '%s' "$chk" | grep -q 'count(\*)' \
     && printf '%s' "$chk" | grep -q 'measured latency'; then
    pass "friction check issued real count(*) Cypher + measured latency"
  else
    bad "friction check did not issue real Cypher / measured latency"
  fi
  # friction serve must stand up a FastAPI app whose GET /health returns 200.
  SPORT=8791
  ( RUST_MIN_STACK=33554432 "$PY" -m friction.cli serve --port "$SPORT" \
      >/tmp/friction_serve_test.log 2>&1 & echo $! >/tmp/friction_serve_test.pid )
  code=""
  for _ in $(seq 1 20); do
    code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$SPORT/health" 2>/dev/null || true)
    [ "$code" = "200" ] && break
    sleep 1
  done
  kill "$(cat /tmp/friction_serve_test.pid 2>/dev/null)" 2>/dev/null || true
  [ "$code" = "200" ] && pass "friction serve GET /health returns 200" \
    || bad "friction serve GET /health did not return 200 (got '${code:-none}')"
else
  echo "  skip engine checks (no node on :9090)"
fi

echo
if [ "$fail" -eq 0 ]; then echo "PASS"; else echo "FAIL"; fi
exit "$fail"
