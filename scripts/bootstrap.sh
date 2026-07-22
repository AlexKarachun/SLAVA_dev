#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEPS_DIR="${SLAVA_DEPS_DIR:-$(cd "${PROJECT_ROOT}/.." && pwd)}"
RUN_SMOKE_TEST=1
DOWNLOAD_LIBERO_DATASETS=1

LIBERO_URL="https://github.com/Lifelong-Robot-Learning/LIBERO.git"
LIBERO_COMMIT="8f1084e3132a39270c3a13ebe37270a43ece2a01"
SIMPLER_URL="https://github.com/simpler-env/SimplerEnv.git"
SIMPLER_COMMIT="06accaca93535902d408da4855f21cece12bceb7"

usage() {
  echo "Usage: $0 [--deps-dir PATH] [--skip-libero-datasets] [--skip-smoke-test]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --deps-dir)
      DEPS_DIR="$2"
      shift 2
      ;;
    --skip-smoke-test)
      RUN_SMOKE_TEST=0
      shift
      ;;
    --skip-libero-datasets)
      DOWNLOAD_LIBERO_DATASETS=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

mkdir -p "${DEPS_DIR}"
DEPS_DIR="$(cd "${DEPS_DIR}" && pwd)"
LIBERO_ROOT="${DEPS_DIR}/LIBERO"
SIMPLER_ROOT="${DEPS_DIR}/SimplerEnv"

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

echo "Project: ${PROJECT_ROOT}"
echo "Dependencies: ${DEPS_DIR}"
echo "Conda: ${CONDA_BIN}"

ensure_repo() {
  local url="$1"
  local path="$2"
  local commit="$3"
  local recurse="$4"

  if [[ ! -e "${path}" ]]; then
    if [[ "${recurse}" == "yes" ]]; then
      git clone --recurse-submodules "${url}" "${path}"
    else
      git clone "${url}" "${path}"
    fi
  elif [[ ! -d "${path}/.git" ]]; then
    echo "${path} exists but is not a Git repository; refusing to overwrite it." >&2
    exit 1
  fi

  if [[ -n "$(git -C "${path}" status --porcelain)" ]]; then
    current="$(git -C "${path}" rev-parse HEAD)"
    if [[ "${current}" != "${commit}" ]]; then
      echo "${path} has local changes and is not at ${commit}; refusing to switch commits." >&2
      exit 1
    fi
  else
    if ! git -C "${path}" cat-file -e "${commit}^{commit}" 2>/dev/null; then
      git -C "${path}" fetch origin "${commit}"
    fi
    git -C "${path}" checkout --detach "${commit}"
  fi

  if [[ "${recurse}" == "yes" ]]; then
    git -C "${path}" submodule update --init --recursive
  fi
  echo "Ready: ${path} @ $(git -C "${path}" rev-parse --short HEAD)"
}

ensure_env() {
  local name="$1"
  local python_version="$2"
  if ! "${CONDA_BIN}" run -n "${name}" python -V >/dev/null 2>&1; then
    "${CONDA_BIN}" create -n "${name}" "python=${python_version}" -y
  fi
}

ensure_repo "${LIBERO_URL}" "${LIBERO_ROOT}" "${LIBERO_COMMIT}" no
ensure_repo "${SIMPLER_URL}" "${SIMPLER_ROOT}" "${SIMPLER_COMMIT}" yes

ensure_env slava-notebook 3.11
"${CONDA_BIN}" run -n slava-notebook python -m pip install \
  -r "${PROJECT_ROOT}/requirements-notebook.txt"

ensure_env slava-libero 3.8.13
"${CONDA_BIN}" run -n slava-libero python -m pip install \
  -r "${LIBERO_ROOT}/requirements.txt"
"${CONDA_BIN}" run -n slava-libero python -m pip install \
  'torch==1.11.0+cu113' 'torchvision==0.12.0+cu113' 'torchaudio==0.11.0' \
  --extra-index-url https://download.pytorch.org/whl/cu113
"${CONDA_BIN}" run -n slava-libero python -m pip install -e "${LIBERO_ROOT}"
"${CONDA_BIN}" run -n slava-libero python -m pip install huggingface_hub

LIBERO_CONFIG_DIR="${LIBERO_CONFIG_PATH:-${HOME}/.libero}"
"${CONDA_BIN}" run -n slava-libero python "${PROJECT_ROOT}/scripts/configure_libero.py" \
  --repo "${LIBERO_ROOT}" --config-dir "${LIBERO_CONFIG_DIR}"

LIBERO_DATASET_DIR="${LIBERO_ROOT}/libero/datasets"

dataset_file_count() {
  local directory="$1"
  if [[ ! -d "${directory}" ]]; then
    echo 0
    return
  fi
  find "${directory}" -maxdepth 1 -type f -name '*.hdf5' -print | wc -l
}

libero_dataset_complete() {
  local dataset="$1"
  case "${dataset}" in
    libero_object|libero_goal|libero_spatial)
      [[ "$(dataset_file_count "${LIBERO_DATASET_DIR}/${dataset}")" -eq 10 ]]
      ;;
    libero_100)
      [[ "$(dataset_file_count "${LIBERO_DATASET_DIR}/libero_10")" -eq 10 ]] &&
        [[ "$(dataset_file_count "${LIBERO_DATASET_DIR}/libero_90")" -eq 90 ]]
      ;;
    *)
      echo "Unknown LIBERO dataset: ${dataset}" >&2
      return 2
      ;;
  esac
}

if [[ "${DOWNLOAD_LIBERO_DATASETS}" == "1" ]]; then
  mkdir -p "${LIBERO_DATASET_DIR}"
  for dataset in libero_object libero_goal libero_spatial libero_100; do
    if libero_dataset_complete "${dataset}"; then
      echo "LIBERO dataset already complete: ${dataset}"
      continue
    fi

    echo "Downloading LIBERO dataset from Hugging Face: ${dataset}"
    # The upstream downloader asks before replacing an incomplete directory.
    # Supplying "y" keeps bootstrap non-interactive while allowing recovery.
    printf 'y\n' | "${CONDA_BIN}" run --no-capture-output -n slava-libero \
      python "${LIBERO_ROOT}/benchmark_scripts/download_libero_datasets.py" \
        --download-dir "${LIBERO_DATASET_DIR}" \
        --datasets "${dataset}" \
        --use-huggingface

    if ! libero_dataset_complete "${dataset}"; then
      echo "LIBERO dataset download is incomplete: ${dataset}" >&2
      exit 1
    fi
  done
else
  echo "Skipping LIBERO demonstration datasets."
fi

ensure_env slava-simpler 3.10
"${CONDA_BIN}" run -n slava-simpler python -m pip install \
  -e "${SIMPLER_ROOT}/ManiSkill2_real2sim"
"${CONDA_BIN}" run -n slava-simpler python -m pip install -e "${SIMPLER_ROOT}"
# Run pins after editable installs: their resolvers otherwise upgrade NumPy / setuptools.
"${CONDA_BIN}" run -n slava-simpler python -m pip install \
  'setuptools<81' 'numpy==1.24.4' 'opencv-python<4.10'
"${CONDA_BIN}" run -n slava-simpler python -m pip check

"${CONDA_BIN}" run -n slava-notebook python -c \
  "import pandas, ipywidgets, PIL; print('Notebook imports OK')"
"${CONDA_BIN}" run -n slava-libero python -c \
  "import libero, robosuite, torch, imageio; print('LIBERO imports OK')"
"${CONDA_BIN}" run -n slava-simpler python -c \
  "import simpler_env, mani_skill2_real2sim, sapien, gymnasium; print('SimplerEnv imports OK')"

if [[ "${RUN_SMOKE_TEST}" == "1" ]]; then
  SMOKE_DIR="$(mktemp -d /tmp/slava-bootstrap-smoke.XXXXXX)"
  cleanup() {
    if [[ -n "${SMOKE_DIR:-}" && -d "${SMOKE_DIR}" ]]; then
      rm -rf "${SMOKE_DIR}"
    fi
  }
  trap cleanup EXIT

  MUJOCO_GL=egl MUJOCO_EGL_DEVICE_ID=0 \
    "${CONDA_BIN}" run --no-capture-output -n slava-libero \
    python "${PROJECT_ROOT}/scripts/collect_libero.py" \
      --libero-repo "${LIBERO_ROOT}" \
      --output-root "${SMOKE_DIR}/libero" \
      --suites libero_goal --task-ids 0 --init-state-ids 0 \
      --image-size 128 --settle-steps 0 --fail-fast

  "${CONDA_BIN}" run --no-capture-output -n slava-simpler \
    python "${PROJECT_ROOT}/scripts/collect_simpler.py" \
      --simpler-repo "${SIMPLER_ROOT}" \
      --output-root "${SMOKE_DIR}/simpler" \
      --tasks widowx_stack_cube --episode-ids 0 --fail-fast
  echo "Rendering smoke tests passed."
fi

cat <<EOF

Bootstrap complete.

Repositories:
  LIBERO_ROOT=${LIBERO_ROOT}
  SIMPLERENV_ROOT=${SIMPLER_ROOT}

LIBERO demonstrations:
  ${LIBERO_DATASET_DIR}

VS Code Remote SSH:
  1. Open ${PROJECT_ROOT}
  2. Open notebooks/01_collect_and_review_inventory.ipynb
  3. Select the slava-notebook Conda environment as the notebook kernel

Kernel Python:
  $("${CONDA_BIN}" run -n slava-notebook python -c 'import sys; print(sys.executable)')
EOF
