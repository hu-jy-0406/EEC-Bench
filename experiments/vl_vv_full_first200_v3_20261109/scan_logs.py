"""Scan logs of successful tasks for error, retry and repair lines (grouped, digits masked)."""
import json,glob,re,collections,sys
from pathlib import Path
EXP=Path(sys.argv[1])
pat=re.compile(r'Traceback|Error|error|repair|retry|Retry|timed out|Timeout|429|500 |502|503|stall|WARNING|Warning',)
hits=collections.Counter(); examples=collections.defaultdict(list)
n=0
for p in glob.glob(str(EXP/'runs/claims/*.json')):
    s=json.load(open(p))
    if s['status']!='success': continue
    prog=json.load(open(EXP/'runs'/s['run']/'progress.json'))['tasks'][s['task_id']]
    out=Path(prog['output_dir']); n+=1
    logs=list(out.parent.glob('*.log'))+list((out/'logs').glob('*.log'))
    for lg in logs:
        try: txt=lg.read_text(errors='replace')
        except OSError: continue
        for line in txt.splitlines():
            m=pat.search(line)
            if m:
                key=(lg.name,re.sub(r'\d+','#',line.strip())[:140])
                hits[key]+=1
                if len(examples[key])<2: examples[key].append(s['task_id'])
print('successful tasks scanned',n)
for k,c in hits.most_common(60): print(c,k,examples[k])
