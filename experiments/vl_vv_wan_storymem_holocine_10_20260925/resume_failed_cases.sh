#!/usr/bin/env bash
set -euo pipefail

root=/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench
exp="$root/experiments/vl_vv_wan_storymem_holocine_10_20260925"
py=/vast/users/guangyi.chen/anaconda3/bin/python
api="$root/scripts/openai_api_env.sh"
gpu=0
gpu_uuid=GPU-0f6e743c1254dd2d

record_stage() {
  local case_dir=$1 name=$2 start_ns=$3 end_ns=$4 status=$5
  "$py" - "$case_dir" "$name" "$start_ns" "$end_ns" "$status" <<'PY'
import json, pathlib, sys
case, name, start, end, status = sys.argv[1:]
path = pathlib.Path(case) / 'case_recovery_stages.json'
state = json.loads(path.read_text()) if path.exists() else {'protocol':'vl_vv_case_recovery_timing_v1','stages':[]}
state['stages'].append({'stage':name,'started_epoch_ns':int(start),'finished_epoch_ns':int(end),'status':status,
                        'seconds':max(0,(int(end)-int(start))/1e9)})
path.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
PY
}

run_stage() {
  local case_dir=$1 name=$2
  shift 2
  local start_ns end_ns status=success log
  start_ns=$(date +%s%N)
  log="$case_dir/logs/recovery_${name}.log"
  mkdir -p "$case_dir/logs"
  if "$@" > "$log" 2>&1; then
    status=success
  else
    status=failed
    end_ns=$(date +%s%N)
    record_stage "$case_dir" "$name" "$start_ns" "$end_ns" "$status"
    cat "$log" >&2
    return 1
  fi
  end_ns=$(date +%s%N)
  record_stage "$case_dir" "$name" "$start_ns" "$end_ns" "$status"
}

mark_pipeline_complete() {
  local case_dir=$1 finish_ns=$2
  "$py" - "$case_dir" "$finish_ns" <<'PY'
import json, pathlib, sys
case=pathlib.Path(sys.argv[1]); finish=int(sys.argv[2])
path=case/'case_timing.json'; timing=json.loads(path.read_text())
timing['pipeline_status']='success'; timing['pipeline_finished_epoch_ns']=finish
timing['review_status']='running'; timing['status']='running'
path.write_text(json.dumps(timing,indent=2)+'\n')
PY
}

mark_review_complete() {
  local case_dir=$1 start_ns=$2 finish_ns=$3
  "$py" - "$case_dir" "$start_ns" "$finish_ns" <<'PY'
import json, pathlib, sys
case=pathlib.Path(sys.argv[1]); start=int(sys.argv[2]); finish=int(sys.argv[3])
path=case/'case_timing.json'; timing=json.loads(path.read_text())
timing.update(review_status='success',status='success',review_started_epoch_ns=start,
              review_finished_epoch_ns=finish,finished_epoch_ns=finish)
path.write_text(json.dumps(timing,indent=2)+'\n')
stages=json.loads((case/'case_recovery_stages.json').read_text())
stages['status']='success'
stages['recovery_seconds']=sum(row['seconds'] for row in stages['stages'])
(case/'case_recovery_stages.json').write_text(json.dumps(stages,ensure_ascii=False,indent=2)+'\n')
PY
}

resume_case() {
  local model=$1 episode=$2 case_dir="$exp/$1/$2/case"
  printf 'resume %s %s\n' "$model" "$episode"

  local entity_ok recovery_ok match_ok dino_manifest_ok attached issues_ok review_ok
  entity_ok=$("$py" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("status")=="success")' "$case_dir/entities/run.json" 2>/dev/null || echo False)
  recovery_ok=$("$py" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("status")=="success")' "$case_dir/shot_prompt_recovery/results.json" 2>/dev/null || echo False)
  if [[ $entity_ok != True || $recovery_ok != True ]]; then
    run_stage "$case_dir" detect "$api" "$py" "$root/scripts/run_vl_vv_detection.py" detect \
      --case "$case_dir" --gpu "$gpu" --gpu-uuid "$gpu_uuid" --shot-workers 3 --device cuda
  fi

  match_ok=$("$py" -c 'import pathlib,sys; print((pathlib.Path(sys.argv[1]) / "global_match/result.json").is_file())' "$case_dir")
  if [[ $match_ok != True ]]; then
    run_stage "$case_dir" match "$api" "$py" "$root/scripts/run_vl_vv_detection.py" match --case "$case_dir"
  fi

  dino_manifest_ok=$("$py" -c 'import pathlib,sys; print((pathlib.Path(sys.argv[1]) / "dino/canonical/manifest.json").is_file())' "$case_dir")
  if [[ $dino_manifest_ok != True ]]; then
    run_stage "$case_dir" dino_prepare "$api" "$py" "$root/scripts/run_vl_vv_detection.py" dino_prepare --case "$case_dir"
  fi
  run_stage "$case_dir" dino "$api" "$py" "$root/scripts/run_vl_vv_detection.py" dino \
    --case "$case_dir" --gpu "$gpu" --gpu-uuid "$gpu_uuid"

  attached=$("$py" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("status")=="complete")' "$case_dir/run.json" 2>/dev/null || echo False)
  if [[ $attached != True ]]; then
    run_stage "$case_dir" attach_dino "$api" "$py" "$root/scripts/run_vl_vv_detection.py" attach_dino --case "$case_dir"
  fi

  issues_ok=$("$py" -c 'import pathlib,sys; print((pathlib.Path(sys.argv[1]) / "issue_discovery/result.json").is_file())' "$case_dir")
  if [[ $issues_ok != True ]]; then
    run_stage "$case_dir" issue_discovery "$api" "$py" "$root/scripts/run_vl_vv_detection.py" discover_issues \
      --case "$case_dir" --issue-output "$case_dir/issue_discovery"
  fi
  local pipeline_finish
  pipeline_finish=$(date +%s%N)
  mark_pipeline_complete "$case_dir" "$pipeline_finish"

  review_ok=$("$py" -c 'import pathlib,sys; print((pathlib.Path(sys.argv[1]) / "issue_review/result.json").is_file())' "$case_dir")
  if [[ $review_ok != True ]]; then
    local review_start review_finish
    review_start=$(date +%s%N)
    run_stage "$case_dir" issue_review "$api" "$py" "$root/scripts/run_vl_vv_issue_review.py" \
      --case "$case_dir" --issues "$case_dir/issue_discovery/result.json" --output "$case_dir/issue_review"
    review_finish=$(date +%s%N)
    mark_review_complete "$case_dir" "$review_start" "$review_finish"
  fi
}

resume_case wan22 74Od5-Fmf60_s00006_n4_clean_v2
resume_case holocine 2hEV6a24yXc_s00017_n8_clean_v3_alt8
resume_case holocine 6kwhPKkHFpA_s00007_n4_clean_v2
resume_case holocine kTAOppBVgsU_s00001_n6_clean_v2
