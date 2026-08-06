#!/usr/bin/env bash
# Pull freshly collected rollouts off a collection box, incrementally.
#
# Written to be run repeatedly while collection is still going: it copies only
# episode directories that are not here yet and appends only annotation rows
# whose run_id is new, so an interrupted or repeated run costs nothing and
# cannot double-count. That matters when the remote box is rented by the hour --
# waiting for one final archive risks losing everything if it goes away.
#
#   SLAVA_REMOTE="-p 17571 root@1.2.3.4" scripts/sync_rollouts_from_server.sh
#
# Pools: both sides address the same pool (SLAVA_RUN_POOL, default pilot_v0 --
# see rollouts/RUNS.md). Syncing a remote pool into a different local one would
# mix two code states in one annotations file, which is exactly what pools
# exist to prevent, so the name is shared rather than configurable per side.
#
# Local annotation rows are never overwritten, only appended to, and a row that
# already exists locally always wins.
set -euo pipefail

REMOTE="${SLAVA_REMOTE:?set SLAVA_REMOTE, e.g. \"-p 17571 root@1.2.3.4\"}"
REMOTE_ROOT="${SLAVA_REMOTE_ROOT:-/workspace/SLAVA_dev}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

POOL="${SLAVA_RUN_POOL:-pilot_v0}"
LOCAL_POOL="${PROJECT_ROOT}/rollouts/final/${POOL}"
REMOTE_POOL="${REMOTE_ROOT}/rollouts/final/${POOL}"
LOCAL_ANNOTATIONS="${LOCAL_POOL}/rollout_annotations.jsonl"
LOCAL_EPISODES="${LOCAL_POOL}/episodes"
mkdir -p "${LOCAL_EPISODES}"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

echo "== аннотации"
# shellcheck disable=SC2086
scp ${REMOTE/ /:}"${REMOTE_POOL}/rollout_annotations.jsonl" \
  "${TMP}/remote.jsonl" >/dev/null 2>&1 || {
    # scp's host:path form does not survive the flag-and-host string above on
    # every shell; fall back to streaming it over ssh, which always works.
    # shellcheck disable=SC2086
    ssh ${REMOTE} "cat ${REMOTE_POOL}/rollout_annotations.jsonl" > "${TMP}/remote.jsonl"
  }

python3 - "${TMP}/remote.jsonl" "${LOCAL_ANNOTATIONS}" "${TMP}/new_ids.txt" <<'PY'
import json, sys
remote_path, local_path, out_path = sys.argv[1:4]

def ids(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return {json.loads(l)["run_id"] for l in fh if l.strip()}
    except FileNotFoundError:
        return set()

local = ids(local_path)
new_rows, new_ids = [], []
with open(remote_path, encoding="utf-8") as fh:
    for line in fh:
        if not line.strip():
            continue
        run_id = json.loads(line)["run_id"]
        if run_id not in local:
            new_rows.append(line.rstrip("\n"))
            new_ids.append(run_id)

if new_rows:
    with open(local_path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(new_rows) + "\n")
with open(out_path, "w", encoding="utf-8") as fh:
    fh.write("\n".join(new_ids))
print(f"новых строк: {len(new_ids)}")
PY

count="$(grep -c . "${TMP}/new_ids.txt" || true)"
if [ "${count}" = "0" ]; then
  echo "== эпизоды: нечего забирать"
  exit 0
fi

echo "== эпизоды: ${count} директорий"
mkdir -p "${LOCAL_EPISODES}"
# One tar stream rather than N scp calls: these directories hold one PNG per
# step per camera, so per-file round-trips dominate everything else.
# shellcheck disable=SC2086
ssh ${REMOTE} "cd ${REMOTE_POOL}/episodes && tar -czf - -T -" \
  < "${TMP}/new_ids.txt" | tar -xzf - -C "${LOCAL_EPISODES}"

echo "== готово: $(wc -l < "${LOCAL_ANNOTATIONS}" | tr -d ' ') аннотаций локально"
