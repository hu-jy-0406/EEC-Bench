import re
from run import HERE,read,dump,io
io.safe_compute();rows=[]
for j in read(HERE/'manifest.json')['jobs']:
    d=HERE/'episodes'/j['episode_id'];p=read(d/'input.json')['source']
    text=p['global_prompt']+' '+ ' '.join(s['text'] for s in p['shots'])
    if not re.search(r'(?:five|5)[ -]second|(?:five|5) seconds',text,re.I):
        rows.append(dict(episode_id=j['episode_id'],source_global=p['global_prompt'],candidate_global=read(d/'candidate.json')['global_caption']))
dump(HERE/'duration_source_screen.json',rows);print(rows)
