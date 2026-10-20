#!/usr/bin/env python3
"""Read-only lexical triage, never a substitute for semantic review or auto-edit."""
import json,re
from pathlib import Path
HERE=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_text())
link_words=set('s the a an is are was were be been being has have had with and or of in on at to from by for as her his their its he she they it this that these those person man woman wears wearing hair top jacket shirt clothing covered covering consists consisting adult setting scene room background face visible foreground shoulder sleeve head belongs belong refers refer described description previously earlier respectively other one part light lit'.split())
def terms(s):
    return set(re.findall(r"[a-z]+",s.lower()))
def stem(s):
    for end in ['ing','ed','es','s']:
        if s.endswith(end) and len(s)>len(end)+2:
            s=s[:-len(end)];break
    return s[:-1] if s.endswith('e') and len(s)>3 else s
flags=[];shots=0;added=0
action=re.compile(r'\b(walks?|walking|turns?|turning|enters?|entering|raises?|raising|lowers?|lowering|sits?|sitting|stands?|standing|holds?|holding|moves?|moving|gestures?|points?|pointing|looks?|looking|smiles?|smiling)\b',re.I)
instruction=re.compile(r'\b(ensure|maintain|preserve|must|always|never|cinematic|high quality|zoom|pan|tracking shot)\b',re.I)
for p in sorted((HERE/'batches').glob('*/final.json')):
    src=read(p.parent/'input.json');out=read(p)
    for e,r in zip(src['episodes'],out['episodes']):
        previous=e['global_prompt']
        for s,t in zip(e['shots'],r['shots']):
            shots+=1
            allowed=terms(previous+' '+s['generation_prompt_en'])|link_words
            stems={stem(w) for w in allowed}
            for a in t['additions']:
                added+=1
                novel=sorted(w for w in terms(a['text'])-allowed if stem(w) not in stems)
                triggers=[]
                if novel:triggers.append('novel_content_words')
                if action.search(re.sub(r'\bsitting room\b','room',a['text'],flags=re.I)):triggers.append('possible_pose_or_action_import')
                if instruction.search(a['text']):triggers.append('possible_extra_instruction')
                if triggers:flags.append(dict(batch=p.parent.name,episode_id=e['episode_id'],shot_id=s['shot_id'],
                    triggers=triggers,novel_words=novel,addition=a,original=s['generation_prompt_en']))
            previous+=' '+s['generation_prompt_en']
result={'shots_screened':shots,'additions_screened':added,'flagged_additions':len(flags),'flags_are_not_errors':True,'flags':flags,
        'api_calls':0,'billable_tokens':0,'api_usd':0}
(HERE/'semantic_screen.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ['shots_screened','additions_screened','flagged_additions']},indent=2))
for f in flags:print(f['batch'],f['episode_id'],f['shot_id'],f['triggers'],f['novel_words'],f['addition']['text'])
