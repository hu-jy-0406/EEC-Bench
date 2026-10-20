#!/usr/bin/env python3
"""CPU-only token compatibility audit, with the exact tested Wan wrapper.

Does not create adapted generation prompts or assert semantic self-containment.
Run on an existing low-load compute node, one CPU, USE_TORCH=0.
"""
import csv
import hashlib
import importlib.util
import json
import os
import platform
import re
import socket
import statistics
import time
from pathlib import Path

started = time.monotonic()
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FEAS = ROOT / 'EECBench/experiments/generation_feasibility_20260921'
SOURCE = ROOT / 'EECBench/experiments/source_video_400_20260920/deliverables/candidates_400.jsonl'
PRIORITY = ROOT / 'EECBench/experiments/source_video_priority_20260921'
TOKENIZER = FEAS / 'models/Wan2.2-T2V-A14B/google/umt5-xxl'
WRAPPER = FEAS / 'repos/Wan2.2/wan/modules/tokenizers.py'

assert socket.gethostname().startswith('auh7-1b-gpu-'), 'Run CPU audit on existing allocated compute node.'
assert len(os.sched_getaffinity(0)) == 1, 'Use one checked CPU.'
assert os.environ.get('USE_TORCH') == '0'
assert os.environ.get('TOKENIZERS_PARALLELISM') == 'false'
source_data = SOURCE.read_bytes()
rows = [json.loads(x) for x in source_data.splitlines()]
assert len(rows) == 400 and sum(len(r['shots']) for r in rows) == 2000
spec = importlib.util.spec_from_file_location('audited_wan_tokenizer', WRAPPER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
tokenizer = module.HuggingfaceTokenizer(str(TOKENIZER), seq_len=512, clean='whitespace', local_files_only=True)
import transformers

flat = [(r, s) for r in rows for s in r['shots']]
texts = [s['generation_prompt_en'] for r, s in flat]
global_plus_shot = [r['global_prompt'] + '\n' + s['generation_prompt_en'] for r, s in flat]
# Both paths call the exact wrapper, including ftfy, double HTML unescape and
# whitespace normalization. Nontruncated lengths include all special tokens.
kwargs = dict(return_tensors=None, padding=False, add_special_tokens=True, return_attention_mask=False)
full_ids = tokenizer(texts, truncation=False, **kwargs)
production_ids = tokenizer(texts, **kwargs)
combined_ids = tokenizer(global_plus_shot, truncation=False, **kwargs)
combined_production = tokenizer(global_plus_shot, **kwargs)
lengths = [len(x) for x in full_ids]
combined_lengths = [len(x) for x in combined_ids]
backref = re.compile(r'\b(same|unchanged|return to|back in|back at|as before|remains|remain)\b', re.I)
output = []
for (r, s), raw, combined in zip(flat, lengths, combined_lengths):
    output.append({'episode_id': r['episode_id'], 'shot_id': s['shot_id'],
                   'raw_shot_tokens_including_special': raw,
                   'global_plus_shot_tokens_including_special': combined,
                   'raw_exceeds_512': raw > 512, 'global_plus_shot_exceeds_512': combined > 512,
                   'backreference_text_flag_only': bool(backref.search(s['generation_prompt_en'])),
                   'raw_text_sha256': hashlib.sha256(s['generation_prompt_en'].encode()).hexdigest()})
with (HERE / 'per_shot.csv').open('w') as f:
    writer = csv.DictWriter(f, fieldnames=list(output[0]))
    writer.writeheader()
    writer.writerows(output)


def summary(selected):
    counts = [r['raw_shot_tokens_including_special'] for r in selected]
    combined = [r['global_plus_shot_tokens_including_special'] for r in selected]
    return {'episodes': len({r['episode_id'] for r in selected}), 'shots': len(selected),
            'raw_min': min(counts), 'raw_mean': statistics.mean(counts),
            'raw_median': statistics.median(counts), 'raw_max': max(counts),
            'raw_over_512': sum(x > 512 for x in counts),
            'global_plus_shot_max': max(combined),
            'global_plus_shot_over_512': sum(x > 512 for x in combined),
            'raw_backreference_flagged_shots': sum(r['backreference_text_flag_only'] for r in selected)}


subsets = {'full400': summary(output)}
for name in ['core_100', 'priority_200']:
    ids = set((PRIORITY / (name + '.ids.txt')).read_text().splitlines())
    subsets[name] = summary([r for r in output if r['episode_id'] in ids])
longest = sorted(output, key=lambda r: -r['raw_shot_tokens_including_special'])[:10]
checks = {'source_unchanged': SOURCE.read_bytes() == source_data,
          'exactly_2000_shots': len(output) == 2000,
          'raw_no_truncation': full_ids == production_ids,
          'global_plus_shot_no_truncation': combined_ids == combined_production,
          'all_raw_nonempty': all(t.strip() for t in texts)}
result = {'source_path': str(SOURCE), 'source_sha256': hashlib.sha256(source_data).hexdigest(),
          'tokenizer_path': str(TOKENIZER), 'wrapper_sha256': hashlib.sha256(WRAPPER.read_bytes()).hexdigest(),
          'tokenizer_class': type(tokenizer.tokenizer).__name__, 'tokenizer_is_fast': tokenizer.tokenizer.is_fast,
          'transformers_version': transformers.__version__, 'python': platform.python_version(),
          'tokenizer_files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in TOKENIZER.iterdir() if p.is_file()},
          'text_len': 512, 'add_special_tokens': True, 'clean': 'whitespace',
          'subsets': subsets, 'longest_raw_shots': longest, 'checks': checks,
          'token_limit_compatibility': all(length <= 512 for length in lengths),
          'semantic_self_containment_audited_all_shots': False,
          'global_plus_shot_is_diagnostic_not_recommended_adapter': True,
          'backreference_flags_are_lexical_diagnostics_not_semantic_failure_labels': True,
          'host': socket.gethostname(), 'cpu_affinity': sorted(os.sched_getaffinity(0)),
          'elapsed_seconds': time.monotonic() - started,
          'api_model_calls': 0, 'billable_api_tokens': 0, 'api_usd': 0,
          'gpu_work': False, 'model_weights_loaded': False, 'generation_started': False}
(HERE / 'audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({k: result[k] for k in ['subsets','checks','tokenizer_class','elapsed_seconds','api_usd']}, ensure_ascii=False, indent=2))
