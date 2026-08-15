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
else
  echo "  skip engine checks (no node on :9090)"
fi

echo
if [ "$fail" -eq 0 ]; then echo "PASS"; else echo "FAIL"; fi
exit "$fail"
