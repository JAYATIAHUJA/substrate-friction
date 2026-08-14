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

for f in data/shipped/nodes.ndjson.gz data/shipped/edges.ndjson.gz \
         data/shipped/subgraphs.json data/shipped/engine_cache.json \
         data/shipped/annotations.json data/shipped/manifest.json \
         data/shipped/README.md; do
  [ -s "$f" ] && pass "present & non-empty: $f" || bad "missing/empty: $f"
done

ls data/shipped/resolved/*.json >/dev/null 2>&1 \
  && pass "resolved sets present" || bad "no resolved sets in data/shipped/resolved/"

# Gzipped graph must be valid and match the manifest counts.
if gzip -t data/shipped/nodes.ndjson.gz 2>/dev/null \
   && gzip -t data/shipped/edges.ndjson.gz 2>/dev/null; then
  pass "gz graph files are valid gzip"
  nn=$(gzip -dc data/shipped/nodes.ndjson.gz | wc -l | tr -d ' ')
  ne=$(gzip -dc data/shipped/edges.ndjson.gz | wc -l | tr -d ' ')
  [ "$nn" = "407302" ] && pass "node rows = 407302" || bad "node rows = $nn (want 407302)"
  [ "$ne" = "660231" ] && pass "edge rows = 660231" || bad "edge rows = $ne (want 660231)"
else
  bad "gz graph files are not valid gzip"
fi

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
  # The warm instance (first annotation, no fix sites) must render and exit 0.
  WARM_ID="$("$PY" -c 'import json;print(next(iter(json.load(open("data/shipped/annotations.json")))))')"
  if "$PY" -m friction.cli check --issue "$WARM_ID" >/dev/null 2>&1; then
    pass "friction check --issue $WARM_ID exits 0"
  else
    bad "friction check --issue $WARM_ID failed"
  fi
else
  echo "  skip engine checks (no node on :9090)"
fi

echo
if [ "$fail" -eq 0 ]; then echo "PASS"; else echo "FAIL"; fi
exit "$fail"
