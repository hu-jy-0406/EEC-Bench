#!/usr/bin/env python3
"""Selected low-overhead appearance entrypoint: compact I/O + evaluator role.

Only this process's Codex invocations override the built-in coding-agent base
instructions; credentials, provider, model, reasoning and tool isolation remain.
"""
import argparse
import json
from pathlib import Path
import gs_entity_appearance_compact as compact
import run_wedetect_shot_entities as io

BASE=compact.ROOT/'prompts/appearance/evaluator_base_v1.txt'
PROTOCOL='entity_appearance_compact_v3'
compact.PROTOCOL=PROTOCOL
ORIGINAL_RUN_PROCESS=io.run_process

def evaluation_process(command,prompt,cwd,events,stderr,timeout):
    if command[-1]!='-':raise ValueError('Unexpected model invocation')
    if io.resolve_codex_bin('codex') != 'codex':
        # This is a pipeline-owned evaluator instruction, distinct from Codex's
        # hidden coding-agent prompt, so retain it in the direct API request.
        return ORIGINAL_RUN_PROCESS(command,BASE.read_text()+'\n\n'+prompt,cwd,events,stderr,timeout)
    actual=command[:-1]+['-c','model_instructions_file='+json.dumps(str(BASE)),'-']
    compact.dump(Path(events).parent/'execution_override.json',dict(protocol=PROTOCOL,
        actual_command=actual,model_instructions_file=str(BASE),model_instructions_sha256=compact.sha(BASE),
        scope='This invocation only; no user config changes',
        documentation='https://learn.chatgpt.com/docs/config-file/config-sample'))
    return ORIGINAL_RUN_PROCESS(actual,prompt,cwd,events,stderr,timeout)


def main():
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['prepare','score','report']);p.add_argument('--source',type=Path);p.add_argument('--out',type=Path)
    p.add_argument('--runs',nargs='+',type=Path);p.add_argument('--only',nargs='*');p.add_argument('--workers',type=int,default=3);p.add_argument('--timeout',type=int,default=600)
    p.add_argument('--defer-dino',action='store_true',help='Prepare VLM inputs before independent DINO computation; integrated report joins both')
    a=p.parse_args()
    if a.phase=='prepare':
        compact.prepare(a.source,a.out,defer_dino=a.defer_dino)
        path=a.out/'manifest.json';m=compact.read(path)
        m['source_hashes'].update({str(Path(__file__).resolve()):compact.sha(__file__),str(BASE):compact.sha(BASE)})
        m['base_instructions']=str(BASE);compact.dump(path,m)
    elif a.phase=='score':
        io.run_process=evaluation_process
        compact.score([r.resolve() for r in a.runs],a.workers,a.only,a.timeout)
    else:compact.report([r.resolve() for r in a.runs],a.out)
if __name__=='__main__':main()
