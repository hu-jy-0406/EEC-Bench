import os
os.environ['TOKENIZERS_PARALLELISM']='false'
os.environ['USE_TORCH']='0'
os.environ['USE_TF']='0'
import json,re,hashlib,html
from pathlib import Path
from transformers import AutoTokenizer
import ftfy
root=Path(__file__).resolve().parent
src=root.parent/'source_video_400_20260920/deliverables/candidates_400.jsonl'
tok=AutoTokenizer.from_pretrained(str(root/'tokenizer'),use_fast=True,local_files_only=True)
rows=[]
for r in map(json.loads,src.read_text().splitlines()):
 g=r['global_prompt']; ss=[s['generation_prompt_en'] for s in r['shots']]
 if 'This scene contains' not in g:g=g.strip()+f' This scene contains {len(ss)} shots.'
 p=f'[global caption] {g} [per shot caption] '+ ' [shot cut] '.join(ss)
 p=re.sub(r'\s+',' ',html.unescape(html.unescape(ftfy.fix_text(p))).strip()).strip()
 full=tok(p,add_special_tokens=True,truncation=False,return_offsets_mapping=True)
 cut=tok(p,add_special_tokens=True,truncation=True,max_length=512,padding='max_length',return_offsets_mapping=True)
 ends=[b for a,b in cut['offset_mapping'] if b>a]; end=max(ends)
 starts=[p.index('[per shot caption]')]+[m.start() for m in re.finditer(re.escape('[shot cut]'),p)]
 spans=[(a,starts[i+1] if i+1<len(starts) else len(p)) for i,a in enumerate(starts)]
 statuses=['full' if end>=b else 'partial' if end>a else 'lost' for a,b in spans]
 rows.append(dict(episode_id=r['episode_id'],shot_count=len(ss),tokens=len(full['input_ids']),raw_chars=len(r['global_prompt'])+sum(map(len,ss)),raw_words=len(r['global_prompt'].split())+sum(len(s.split()) for s in ss),prompt=p,retained_end=end,shot_status=statuses,truncated_tokens=len(cut['input_ids'])))
longest=max(rows,key=lambda r:r['tokens'])
(root/'longest_full_prompt.txt').write_text(longest['prompt'])
(root/'longest_retained_text.txt').write_text(longest['prompt'][:longest['retained_end']])
(root/'longest_discarded_text.txt').write_text(longest['prompt'][longest['retained_end']:])
summary={
 'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'tokenizer_class':type(tok).__name__,'truncation_side':tok.truncation_side,
 'tokenizer_files_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'tokenizer').iterdir()},
 'count':len(rows),'over_limit':sum(r['tokens']>512 for r in rows),'longest':{k:v for k,v in longest.items() if k!='prompt'},
 'longest_by_raw_chars':max(rows,key=lambda r:r['raw_chars'])['episode_id'],
 'longest_by_raw_words':max(rows,key=lambda r:r['raw_words'])['episode_id'],
 'by_shot_count':{str(n):{'count':sum(r['shot_count']==n for r in rows),'over_limit':sum(r['shot_count']==n and r['tokens']>512 for r in rows),'min_tokens':min(r['tokens'] for r in rows if r['shot_count']==n),'max_tokens':max(r['tokens'] for r in rows if r['shot_count']==n)} for n in [4,6,8]},
 'api_cost_usd':0,'model_calls':0}
(root/'summary.json').write_text(json.dumps(summary,indent=2))
(root/'all_lengths.json').write_text(json.dumps([{k:v for k,v in r.items() if k!='prompt'} for r in rows],indent=2))
print(json.dumps(summary,indent=2));print('RETAINED TAIL:',longest['prompt'][:longest['retained_end']][-180:])
