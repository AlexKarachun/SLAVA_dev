#!/usr/bin/env bash
# Sets up the three model-specific conda envs used by scripts/run_rollouts.py's
# model-servers (scripts/model_servers/*.py): slava-greenvla, slava-openvla,
# slava-lerobot. Separate from scripts/bootstrap.sh, which only sets up the
# D1-D4 data-authoring envs (slava-notebook/slava-libero/slava-simpler) plus
# the env-workers those two feed (src/slava_rollout/env_worker_*.py).
#
# Reconstructed from the actual installed state of these three envs after a
# debugging session that hit and fixed several real upstream packaging bugs
# (see .claude/skills/slava-greenvla, slava-openvla-oft, slava-lerobot-policies
# for the full "why" behind each pin below) — NOT independently re-verified as
# a single clean end-to-end run on a fresh machine. If a step fails, cross-check
# the exact error against those skill files before improvising a different fix.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEPS_DIR="${SLAVA_DEPS_DIR:-$(cd "${PROJECT_ROOT}/.." && pwd)}"

GREENVLA_URL="https://github.com/greenvla/GreenVLA.git"
GREENVLA_COMMIT="952a80c3f57880b7db4fb9280d1a4ef27b12f843"
OPENVLA_OFT_URL="https://github.com/moojink/openvla-oft.git"
OPENVLA_OFT_COMMIT="e4287e94541f459edc4feabc4e181f537cd569a8"
LEROBOT_URL="https://github.com/huggingface/lerobot.git"
LEROBOT_COMMIT="64b23178d5348609c266250d3e1f511eba4c33ff"

find_conda() {
  if [[ -n "${CONDA_EXE:-}" && -x "${CONDA_EXE}" ]]; then
    echo "${CONDA_EXE}"
  elif command -v conda >/dev/null 2>&1; then
    command -v conda
  elif [[ -x /opt/miniforge3/bin/conda ]]; then
    echo /opt/miniforge3/bin/conda
  elif [[ -x /opt/conda/bin/conda ]]; then
    echo /opt/conda/bin/conda
  else
    return 1
  fi
}

CONDA_BIN="$(find_conda || true)"
if [[ -z "${CONDA_BIN}" ]]; then
  echo "Conda was not found. Install Miniforge/Miniconda or set CONDA_EXE." >&2
  exit 1
fi

mkdir -p "${DEPS_DIR}"
DEPS_DIR="$(cd "${DEPS_DIR}" && pwd)"
GREENVLA_ROOT="${DEPS_DIR}/greenvla_repo"
OPENVLA_OFT_ROOT="${DEPS_DIR}/openvla_oft_repo"
LEROBOT_ROOT="${DEPS_DIR}/lerobot_repo"

echo "Project: ${PROJECT_ROOT}"
echo "Dependencies: ${DEPS_DIR}"
echo "Conda: ${CONDA_BIN}"

ensure_repo() {
  local url="$1" path="$2" commit="$3"
  if [[ ! -e "${path}" ]]; then
    git clone "${url}" "${path}"
  fi
  (cd "${path}" && git fetch origin "${commit}" 2>/dev/null || true && git checkout "${commit}")
}

ensure_env() {
  local name="$1" python_version="$2"
  if ! "${CONDA_BIN}" run -n "${name}" python -V >/dev/null 2>&1; then
    "${CONDA_BIN}" create -n "${name}" "python=${python_version}" -y
  fi
}

# ---------------------------------------------------------------------------
# slava-greenvla (py3.11) — GreenVLA R0/R1/R2, scripts/model_servers/greenvla_server.py
# ---------------------------------------------------------------------------
ensure_repo "${GREENVLA_URL}" "${GREENVLA_ROOT}" "${GREENVLA_COMMIT}"

# GreenVLA's own pyproject.toml doesn't build as-is: [project] has no version
# (their README's `uv sync` tolerates this, plain `pip install -e .` doesn't),
# and [tool.poetry] doesn't declare `packages`, so poetry-core looks for a
# `greenvla/` directory that doesn't exist (their code lives under `lerobot/`
# — this repo is an old vendored lerobot fork, confusingly named). Both are
# local packaging workarounds for OUR install only, not upstream changes.
python3 - "${GREENVLA_ROOT}/pyproject.toml" <<'PYEOF'
import re, sys
path = sys.argv[1]
text = open(path).read()
if 'version = "0.0.0"' not in text:
    text = text.replace(
        'name = "greenvla"\n',
        'name = "greenvla"\nversion = "0.0.0"\n',
        1,
    )
if "packages = [{include" not in text:
    text = text.replace(
        "requires-poetry = \">=2.1\"\n",
        "requires-poetry = \">=2.1\"\npackages = [{include = \"lerobot\"}]\n",
        1,
    )
open(path, "w").write(text)
PYEOF

ensure_env slava-greenvla 3.11
# Pin torch BEFORE `pip install -e .` — an unpinned resolver picks
# torch==2.11.0+cu130 by default, which only supports compute capability
# >=7.5 and warns/underperforms on older GPUs (e.g. V100, cc=7.0). This is
# the same version GreenVLA's own pyproject.toml pins upstream.
"${CONDA_BIN}" run -n slava-greenvla python -m pip install \
  'torch==2.7.1' --index-url https://download.pytorch.org/whl/cu126
"${CONDA_BIN}" run -n slava-greenvla python -m pip install -e "${GREENVLA_ROOT}"
"${CONDA_BIN}" run -n slava-greenvla python -m pip install transforms3d scipy flask requests

# ---------------------------------------------------------------------------
# slava-openvla (py3.10) — OpenVLA-OFT, scripts/model_servers/openvla_oft_server.py
# ---------------------------------------------------------------------------
ensure_repo "${OPENVLA_OFT_URL}" "${OPENVLA_OFT_ROOT}" "${OPENVLA_OFT_COMMIT}"

ensure_env slava-openvla 3.10
"${CONDA_BIN}" run -n slava-openvla python -m pip install \
  'torch==2.2.0' 'torchvision==0.17.0' --index-url https://download.pytorch.org/whl/cu121
"${CONDA_BIN}" run -n slava-openvla python -m pip install -e "${OPENVLA_OFT_ROOT}"
# openvla-oft's inference-only code path eagerly imports tensorflow/
# tensorflow_datasets/dlimp (via prismatic/vla/datasets/rlds/, used for RLDS
# training datasets we never touch) — its declared tensorflow==2.15.0 pin
# drags in a protobuf that's incompatible with tensorflow_metadata's compiled
# _pb2.py (gencode/runtime version guarantee violation). Upgrading both lifts
# the conflicting protobuf<5 ceiling; pip will warn about the declared pin
# mismatch, that warning is expected and harmless (tensorflow is never on the
# actual inference path).
"${CONDA_BIN}" run -n slava-openvla python -m pip install 'tensorflow>=2.16' 'protobuf>=6.31.1,<7'
"${CONDA_BIN}" run -n slava-openvla python -m pip install scipy flask requests

# ---------------------------------------------------------------------------
# slava-lerobot (py3.12) — pi0/pi0.5/SmolVLA, scripts/model_servers/lerobot_server.py
# ---------------------------------------------------------------------------
ensure_repo "${LEROBOT_URL}" "${LEROBOT_ROOT}" "${LEROBOT_COMMIT}"

# huggingface/lerobot's pyproject.toml requires python>=3.12 (not 3.10/3.11 —
# don't assume from the other two envs above).
ensure_env slava-lerobot 3.12
"${CONDA_BIN}" run -n slava-lerobot python -m pip install \
  'torch==2.7.1' --index-url https://download.pytorch.org/whl/cu126
"${CONDA_BIN}" run -n slava-lerobot python -m pip install -e "${LEROBOT_ROOT}"
# scipy: scripts/model_servers/*.py all do `from scipy.spatial.transform import
# Rotation` at module level. It reached slava-greenvla/slava-openvla as a
# transitive dependency and slava-lerobot not at all, so on a clean machine the
# lerobot model-server died on import and every episode waited out the 600s
# health timeout. Declared explicitly for all three envs now (found 2026-08-06
# on the first genuinely-from-scratch install).
"${CONDA_BIN}" run -n slava-lerobot python -m pip install scipy flask requests

echo ""
echo "Done. Sanity-check each env, e.g.:"
echo "  ${CONDA_BIN} run -n slava-greenvla python -c 'from lerobot.common.policies.factory import load_pretrained_policy'"
echo "  ${CONDA_BIN} run -n slava-openvla python -c 'import prismatic'"
echo "  ${CONDA_BIN} run -n slava-lerobot python -c 'from lerobot.policies.factory import get_policy_class'"
echo "(NOTE: lerobot_server.py imports from lerobot.policies.* — no 'common' —"
echo " unlike GreenVLA's vendored fork, which uses lerobot.common.policies.*."
echo " Same top-level package name, different, incompatible internal layout;"
echo " don't cross-reference import paths between slava-greenvla and slava-lerobot.)"
echo "Then smoke-test the actual pipeline: conda run -n slava-notebook python scripts/run_rollouts.py --smoke-test"
