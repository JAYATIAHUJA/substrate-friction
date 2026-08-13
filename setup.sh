#!/usr/bin/env bash
# =============================================================================
# Substrate Friction — one-command setup.
#
#   git clone <repo> && cd substrate-friction && ./setup.sh
#
# From a clean clone this brings up the engine, installs the package, loads the
# SHIPPED pre-built subgraphs (no tree-sitter, no Django re-parse), and warms a
# real `friction check`. No manual steps. `just` is NOT required.
# =============================================================================
set -euo pipefail

# Run from the repo root regardless of where the script is invoked from.
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Substrate Friction setup"

# ---------------------------------------------------------------------------
# 1. Data dirs, dev token, permissions for the UID-10001 container user.
# ---------------------------------------------------------------------------
mkdir -p hydradb-data/graph hydradb-data/cache minio-data secrets \
         data/instances/resolved

if [ ! -f secrets/token ]; then
  # 32-byte dev token; matches Settings.from_env() default and GRAPH_ALLOW_PLAINTEXT.
  printf 'local-development-token-32-bytes' > secrets/token
fi

# The image runs as UID/GID 10001 and LOCAL_PATH must already exist and be
# writable by that user. chown if we can; otherwise widen the mode so the
# container user can write (best-effort, never fatal).
if command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
  sudo chown -R 10001:10001 hydradb-data minio-data || true
else
  chmod -R 0777 hydradb-data minio-data || true
fi

# ---------------------------------------------------------------------------
# 2. Materialise data/instances/ from the shipped payload.
#    data/instances/ is .gitignore'd, so a clean clone has none of the files
#    the CLI reads (subgraphs manifest, engine cache, annotations, resolved
#    sets). Copy them from data/shipped/ where they ARE committed.
# ---------------------------------------------------------------------------
echo "==> materialising data/instances/ from data/shipped/"
cp -f data/shipped/subgraphs.json    data/instances/subgraphs.json
cp -f data/shipped/engine_cache.json data/instances/engine_cache.json
cp -f data/shipped/annotations.json  data/instances/annotations.json
cp -f data/shipped/resolved/*.json   data/instances/resolved/

# ---------------------------------------------------------------------------
# 3. Bring up the stack and wait for readiness.
# ---------------------------------------------------------------------------
echo "==> starting graph-node and MinIO"
docker compose up -d graph-node minio

echo -n "==> waiting for /readyz"
ready=0
for _ in $(seq 1 120); do
  if curl -sf http://127.0.0.1:9090/readyz >/dev/null 2>&1; then
    echo " ready"; ready=1; break
  fi
  echo -n "."; sleep 1
done
if [ "$ready" -ne 1 ]; then
  echo
  echo "ERROR: engine did not become ready. Recent logs:" >&2
  docker compose logs --tail 40 graph-node >&2 || true
  exit 1
fi

# ---------------------------------------------------------------------------
# 4. Install the Python package (editable — the `friction` console script is
#    dead otherwise). Prefer uv; fall back to venv+pip.
# ---------------------------------------------------------------------------
if command -v uv >/dev/null 2>&1; then
  echo "==> uv sync (installs the package editable)"
  uv sync --extra dev
  RUN=(uv run)
else
  echo "==> creating .venv and installing editable with pip"
  python3 -m venv .venv
  # shellcheck disable=SC1091
  . .venv/bin/activate
  pip install --quiet -e '.[dev]'
  RUN=()
fi

# ---------------------------------------------------------------------------
# 5. Probe engine capabilities (also (re)writes docs/engine-capabilities.md,
#    which the loader reads to pick the statement forms this build accepts).
# ---------------------------------------------------------------------------
echo "==> probing engine capabilities"
"${RUN[@]}" python -m friction.probe

# ---------------------------------------------------------------------------
# 6. Load the shipped pre-built subgraphs — unless they are already resident.
#    The edge loader uses CREATE, so re-loading would duplicate edges AND add
#    needless writes toward the object-store defect. Guard on a known seed id.
# ---------------------------------------------------------------------------
echo "==> checking whether the graph is already loaded"
if "${RUN[@]}" python - <<'PY'
import sys
from friction.client import connect
from friction.config import Settings
t = connect(Settings.from_env(), prefer="bolt")
try:
    rows = t.query("MATCH (n {sid: '4020005905'}) RETURN n.id AS id")
finally:
    t.close()
sys.exit(0 if rows else 1)
PY
then
  echo "    already loaded — skipping load (safe re-run)."
else
  echo "==> loading the pre-built subgraphs (407,302 nodes / 660,231 edges)"
  echo "    one-time load; ~2 min. The engine caps ingest at a 1024-item batch,"
  echo "    so edge ingest (~7.4k edges/s) dominates. No re-parse of Django."
  gunzip -kf data/shipped/nodes.ndjson.gz data/shipped/edges.ndjson.gz
  "${RUN[@]}" python -m friction.loader --dir data/shipped
  # Reclaim the ~30 MB of decompressed NDJSON; the .gz copies are the source.
  rm -f data/shipped/nodes.ndjson data/shipped/edges.ndjson
fi

# ---------------------------------------------------------------------------
# 7. Warm a real end-to-end `friction check`. The first annotated instance has
#    no fix sites, so it renders instantly and cannot time out — a safe warm
#    that proves the whole path (engine -> paths -> metric -> gate) runs.
#    `friction check` exits 0 even on an engine timeout, so this never blocks.
# ---------------------------------------------------------------------------
WARM_ID="$("${RUN[@]}" python -c 'import json;print(next(iter(json.load(open("data/shipped/annotations.json")))))')"
echo "==> warming: friction check --issue ${WARM_ID}"
"${RUN[@]}" friction check --issue "${WARM_ID}" >/dev/null 2>&1 || true

# ---------------------------------------------------------------------------
# Done.
# ---------------------------------------------------------------------------
cat <<EOF

Ready. The engine is loaded and the gate runs. Try:

  ${RUN[*]:-} friction list
  ${RUN[*]:-} friction check --issue django__django-10880 --max-len 4
  ${RUN[*]:-} friction eval        # the recorded NO-GO verdict (AUC 0.565, p=0.726)
  ${RUN[*]:-} friction fidelity    # why the engine's AUC 0.780 is a truncation artifact

Note: at maxLen 6 the cohort median query is ~14.6 s and 20 of 43 instances time
out or OOM; --max-len 4 trades reach for a query the engine answers quickly.
EOF
