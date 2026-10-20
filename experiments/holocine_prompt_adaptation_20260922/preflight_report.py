#!/usr/bin/env python3
"""Local-only audit and reviewable source-preserving native input baselines."""
import collections,csv,json,pathlib,statistics
from run import HERE,ROOT,read,dump,sha,render,io

def main():
    io.safe_compute()
    m=read(HERE/'manifest.json');jobs=m['jobs'];rows=[]
    pilot_ids=set(read(HERE/'pilot.json')['episode_ids'])
    for j in jobs:
        d=HERE/'episodes'/j['episode_id'];p=read(d/'input.json');c=read(d/'contract.json')
        assert sha(d/'contract.json')==j['contract_sha256']
        assert sha(d/'alignment_contract.json')==j['alignment_contract_sha256']
        candidate=dict(global_caption=p['source']['global_prompt'],shots=[dict(shot_id=s['shot_id'],caption=s['text']) for s in p['source']['shots']])
        n=j['shot_count'];text=render(candidate)
        # Raw Mode 2; do not invoke the helper that appends extra prose.
        dump(d/'source_native_baseline.json',dict(status='unadapted_source_baseline_NOT_approved_for_generation',prompt=text,source_shot_ids=[s['shot_id'] for s in p['source']['shots']],token_audit=read(d/'original_token_audit.json')))
        dump(d/'shot_mapping.json',[dict(shot_id=s['shot_id'],holo_shot_index=i,contract_schedule_key=s['schedule_key']) for i,s in enumerate(p['source']['shots'])])
        if j['episode_id'] in pilot_ids:
            q=HERE/'outbound_preview'/j['episode_id'];q.mkdir(parents=True,exist_ok=True)
            (q/'draft_request.txt').write_text((HERE/'draft.txt').read_text()+'\nINPUT_JSON:\n'+json.dumps(p,ensure_ascii=False,separators=(',',':')))
        rows.append(dict(rank=j['rank'],episode_id=j['episode_id'],shots=n,claims=j['claims'],native_tokens=j['original_tokens'],over_limit=max(0,j['original_tokens']-512),fits_512=j['original_tokens']<=512))
    with (HERE/'length_audit.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    groups=[]
    for n in [4,6,8]:
        a=[r for r in rows if r['shots']==n]
        groups.append(dict(shots=n,episodes=len(a),fits=sum(r['fits_512'] for r in a),over=sum(not r['fits_512'] for r in a),min_tokens=min(r['native_tokens'] for r in a),mean_tokens=statistics.mean(r['native_tokens'] for r in a),max_tokens=max(r['native_tokens'] for r in a)))
    audit=dict(status='local_preflight_complete_semantic_adaptation_pending',episodes=len(rows),shots=sum(r['shots'] for r in rows),claims=sum(r['claims'] for r in rows),source_and_contract_unchanged=True,source_revisions_preserved=True,groups=groups,native_token_limit_including_special=512,model_calls=0,api_tokens=0,api_usd=0,auto_review_block='Explicit approval pending for current episode prompt/contract texts to configured Codex service; no external model calls executed.',tokenizer_source_sha256=m['source_hashes'][str(ROOT/'EECBench/experiments/generation_feasibility_20260921/repos/HoloCine/diffsynth/prompters/wan_prompter.py')])
    dump(HERE/'preflight_audit.json',audit)
    lines=['# HoloCine 400-episode prompt adaptation: local preflight','',
      'Status: local preparation complete; semantic adaptation NOT complete. The user requires no missing or added information and compatibility with existing frozen contracts. No candidate has been released for generation.',
      '', 'Authoritative inputs: current source priority queue and original contract.json / alignment_contract.json, including all three approved source revisions. All 400 episode IDs, 2,000 shots, 64,724 claims and schedules remain unchanged.',
      '', '## Actual input constraint','',
      'The deployed native HoloCine UMT5 tokenizer truncates the complete episode at 512 tokens, including global/per-shot delimiters and EOS. The preflight executes its original tokenizer class and text cleaners, compares untruncated vs production token IDs, and records all global/shot token spans. No text encoder/GPU is loaded.',
      '', '| Shots/episode | Episodes | Fit without compression | Over512 | Min / mean / max tokens |','|---|---:|---:|---:|---|']
    for g in groups:lines.append(f"|{g['shots']}|{g['episodes']}|{g['fits']}|{g['over']}|{g['min_tokens']} / {g['mean_tokens']:.1f} / {g['max_tokens']}|")
    lines+=['','This measures original native-format input only. It does not prove lossless compression impossible. Token fit alone does not certify semantic equivalence or per-shot conditioning; formal candidates require both mechanical and independent semantic gates.',
      '', '## Reviewable next action','',
      'Four source-selected pilots cover 4/6/8 shots and the longest native text. Exact text-only draft requests are under outbound_preview/. The proposed configured service is Codex / gpt-6-astra, medium reasoning. Independent review checks every original claim, every schedule member, source-only details and added facts. Prompts and schemas are saved locally. No images, videos, credentials, generated evidence or outside context are provided.',
      '', 'Automatic approval review rejected the first launch because authorization for disclosing this specific prompt/contract payload was not recognized. Explicit user approval has been requested; no workaround or alternate external destination is used.',
      '', 'No per-episode semantic call has run. API usage: 0 calls / 0 tokens / USD0. CPU-only preflight reused existing allocation206117, node306, verified low-utilization CPUs60-63; GPUs hidden. Existing Wan/StoryMem campaigns and source prompts/contracts are unchanged.',
      '', '## Artifacts','',
      '- length_audit.csv: all400 native token counts and overflow.',
      '- episodes/<id>/source_native_baseline.json: exact source text in native raw-input format; explicitly NOT approved for generation.',
      '- episodes/<id>/contract.json and alignment_contract.json: byte-preserved originals.',
      '- episodes/<id>/shot_mapping.json: original Shot IDs to Holo indices and contract schedule keys.',
      '- outbound_preview/<id>/draft_request.txt: exact reviewable pilot outbound text.',
      '- draft.txt / review.txt / *.schema.json / run.py: bounded model workflow and fail-closed gates.',
      '', 'Official format: https://github.com/yihao-meng/HoloCine#prompt-format . Existing 512 limit, model architecture, shot durations, schedules and evaluation criteria are not modified.']
    (HERE/'REPORT.md').write_text('\n'.join(lines)+'\n');print(json.dumps(audit),flush=True)

if __name__=='__main__':main()
