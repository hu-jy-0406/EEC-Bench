#!/usr/bin/env bash
# Run INSIDE an existing allocation after checking physical GPU availability.
set -euo pipefail
if [[ $# -lt 3 ]]; then
  echo 'Usage: run_local_detector.sh PHYSICAL_GPU PYTHON_BIN [detect_keyframes_local.py arguments...]' >&2
  exit 2
fi
physical_gpu=$1
python_bin=$2
shift 2
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# Do not combine HIP and ROCr masks: HIP indices are relative to the ROCr mask.
unset HIP_VISIBLE_DEVICES CUDA_VISIBLE_DEVICES
if [[ "$physical_gpu" == GPU-* ]]; then
  export ROCR_VISIBLE_DEVICES="$physical_gpu"
else
  export ROCR_VISIBLE_DEVICES="$physical_gpu"
fi
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false
runtime_dir=$(mktemp -d /tmp/eec-local-detector.XXXXXX)
export MIOPEN_USER_DB_PATH="$runtime_dir/miopen-db"
export MIOPEN_CUSTOM_CACHE_DIR="$runtime_dir/miopen-cache"
export XDG_CACHE_HOME="$runtime_dir/cache"
export YOLO_CONFIG_DIR="$runtime_dir/ultralytics"
mkdir -p "$MIOPEN_USER_DB_PATH" "$MIOPEN_CUSTOM_CACHE_DIR" "$XDG_CACHE_HOME" "$YOLO_CONFIG_DIR"
exec "$python_bin" "$script_dir/detect_keyframes_local.py" "$@"
