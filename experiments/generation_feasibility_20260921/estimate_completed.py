"""Summarize completed measurements only; no GPU or inference calls."""
import json
from pathlib import Path
from statistics import mean
R = Path(__file__).resolve().parent
out = {"status": "partial_until_all_models_complete", "episodes": 400, "shots": 2000,
       "api_calls": 0, "api_cost_usd": 0,
       "excludes": ["one-time downloads/setup", "downstream evaluation", "queueing/retries"],
       "assumptions": ["same MI210 and settings", "adequate host RAM", "continuous availability"]}
p = R / "wan_outputs/timings.json"
if p.exists():
    w = json.loads(p.read_text())
    rows = [x for x in w["shots"] if x["frames"] == 81 and x["steps"] == 40]
    if rows:
        secs = [x["generation_seconds"] + x["save_seconds"] for x in rows]
        out["wan"] = {"samples": len(rows), "shot_seconds": secs,
            "mean_shot_seconds": mean(secs), "projection_seconds_400": 2000 * mean(secs),
            "projection_days_one_gpu": 2000 * mean(secs) / 86400,
            "worker_init_seconds_extra": w["load_seconds"],
            "mode": "measured_full_steps_per_shot_extrapolation"}
h = {}
for shots, frames, count in [(4,321,240),(6,481,120),(8,641,40)]:
    folder = R / f"outputs/holocine/{shots}shot_{frames//16}s_2step"
    p = folder / "metrics.json"
    sp = folder / "step_times.jsonl"
    if not p.exists() or not sp.exists():
        continue
    m = json.loads(p.read_text())
    if m.get("status") != "complete":
        continue
    steps = [json.loads(x) for x in sp.read_text().splitlines() if x.strip()]
    assert len(steps) == 2 and [s["step"] for s in steps] == [0, 1]
    assert m["args"]["frames"] == frames and m["args"]["steps"] == 2
    costs = [s["seconds"] for s in steps]
    overhead = m["generation_seconds"] - sum(costs)
    assert overhead >= 0
    projected = overhead + 50 * mean(costs) + m["encoding_seconds"]
    h[str(shots)] = {"episodes": count, "frames": frames, "measured_step_seconds": costs,
        "non_step_generation_seconds": overhead, "encoding_seconds": m["encoding_seconds"],
        "projection_50step_episode_seconds": projected,
        "projection_total_seconds": count * projected,
        "load_seconds_per_worker_or_episode_extra": m["load_seconds"]}
out["holocine"] = {"mode": "two_step_full_duration_projection_to_50_steps_NOT_full_length_50step_measurement",
    "length_measurements": h, "complete_length_coverage": len(h) == 3,
    "limitations": ["two-step probe has one high and one low expert step; 50-step run has 21 high and 29 low",
                    "per-step times include expert-switch and warmup costs, amplified by scaling",
                    "CFG positive/negative forwards already included; do not multiply by two",
                    "worker initialization and validation excluded from core projection",
                    "16fps is benchmark duration adaptation; official entrypoint uses 15fps"]}
if len(h) == 3:
    total = sum(x["projection_total_seconds"] for x in h.values())
    out["holocine"].update(projection_seconds_400=total, projection_days_one_gpu=total/86400)
sm = json.loads((R / "storymem_metrics.json").read_text())
sc = sm.get("composition_projection_400episodes")
out["storymem"] = {"status": sm["status"], "composition": sc}
if sc:
    proxy = sc["missing_first_encode_proxy_additional_hours"]
    hours = sc["low_memory_mean_hours"] + proxy
    high = sc["cap10_compute_shape_scenario_hours"] + proxy
    out["storymem"].update(projection_hours_400=hours, projection_days_one_gpu=hours/24,
        cap10_conditional_hours=high, cap10_conditional_days=high/24,
        first_encode_assumption="unmeasured; uses mean of measured later-shot encoding", 
        limitations="low-memory chain observed 0/1/2/2 input memories; cap10 is selector-bypass two-step diagnostic, not full40step measurement or strict bound")
    if "projection_seconds_400" in out["holocine"]:
        base = (out["wan"]["projection_seconds_400"] + out["holocine"]["projection_seconds_400"]) / 3600
        out["pooled_parallel_projection"] = {"scope": "each model400episodes,1200total; balanced independent workers on identical MI210; ideal only, excludes queues/retries/validation and Wan/Holo worker load",
            "total_single_gpu_hours_low_memory": base + hours,
            "total_single_gpu_hours_cap10_scenario": base + high,
            "ideal_days": {str(n): {"low_memory": (base+hours)/24/n, "cap10_scenario": (base+high)/24/n} for n in [4,8,16,32]}}
if sm["status"].startswith("complete") and out["holocine"]["complete_length_coverage"] and out["wan"]["samples"] >= 2:
    out["status"] = "complete_measurements_with_explicit_extrapolations"
(R / "runtime_estimates.json").write_text(json.dumps(out, indent=2)+"\n")
print(json.dumps(out, indent=2))
