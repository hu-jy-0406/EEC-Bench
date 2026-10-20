# Complete

400 native episode scripts / 2,000 shots. Independent audit and archive
integrity checks passed. All task processes finished; no model call remains.

Use deliverables/episodes/<episode_id>/story_script.json as the StoryMem
--story_script_path. Dispatch references are relative to deliverables/.
Core100, cumulativePriority200 and Full400 order retained.

Native inputs contain current corrected text and unchanged reviewed context
suffixes. No old contradictory version is included in the generated inputs.
Full mapping and checks: REPORT.md, independent_validation.json, index.json.
Bundle: storymem_prompts_400.zip, with adjacent SHA256 file.

Reproduction environment: existing compute node, one checked CPU, nice10,
USE_TORCH=0 USE_TF=0 HF_HUB_OFFLINE=1 TOKENIZERS_PARALLELISM=false;
PYTHONPATH includes generation_feasibility_20260921/storymem_deps and deps;
vace/bin/python build.py (fresh output directory only), then verify.py.
First verify startup missed the common deps/JSON5 path; corrected scoped
PYTHONPATH, final verification exited0. Shared environments unchanged.

New model calls0, billable API tokens0, API USD0; no video generation.
