#!/usr/bin/env python3
"""Audit isolation manifests and then independently audit each single-shot graph."""
import argparse
import json
from pathlib import Path
from audit_shot_static_3d import audit
import run_wedetect_shot_entities as io
import run_isolated_shot_static_3d as runner


def run(root):
    directories = [root/'shot1', root/'shot3']
    contexts, threads, results = [], [], []
    for directory in directories:
        sid = directory.name
        review_dir = directory/'review'
        request = io.read(review_dir/'request.json')
        payload = io.read(review_dir/'input.json')
        source = io.read(directory/'source_shot.json')
        assert len(source['shots']) == 1 and source['shots'][0]['shot_id'] == sid
        assert payload == runner.make_payload(source['shots'][0])
        expected_prompt = (runner.transport.PROMPTS/runner.PROMPT).read_text() + '\nINPUT_JSON:\n' + json.dumps(payload, ensure_ascii=False)
        assert (review_dir/'prompt.txt').read_text() == expected_prompt
        assert payload['shot_id'] == sid
        assert all(e['entity_id'].startswith(sid+'/') for e in payload['entities'])
        assert len(payload['frames']) == len(request['images']) == 6
        expected = source['shots'][0]['calibration']['images']
        assert [(x['frame_id'], x['sha256']) for x in request['images']] == [(x['frame_id'], x['sha256']) for x in expected]
        assert {x['shot_id'] for x in request['images']} == {sid}
        assert request['prompt_sha256'] == io.sha(review_dir/'prompt.txt')
        assert request['schema_sha256'] == io.sha(review_dir/'output.schema.json')
        command = request['command']
        assert '--ephemeral' in command and '--ignore-user-config' in command
        assert command[command.index('--sandbox')+1] == 'read-only'
        assert 'project_doc_max_bytes=0' in command
        skill_settings = [x for x in command if x.startswith('skills.config=')]
        assert len(skill_settings) == 1 and 'enabled=false' in skill_settings[0] and 'enabled=true' not in skill_settings[0]
        disabled = {command[i+1] for i,x in enumerate(command[:-1]) if x=='--disable'}
        assert {'shell_tool','unified_exec','view_image','apps','plugins','memories','multi_agent','skill_search'} <= disabled
        assert command.count('--image') == 6
        contexts.append(command[command.index('--cd')+1])
        other = 'shot3' if sid=='shot1' else 'shot1'
        assert other not in (review_dir/'prompt.txt').read_text()
        events = [json.loads(line) for line in (review_dir/'events.jsonl').read_text().splitlines()]
        ids = [e['thread_id'] for e in events if e.get('type')=='thread.started']
        assert len(ids) == 1
        threads += ids
        usage = io.audit_events(review_dir/'events.jsonl')
        result = audit(directory/'source_shot.json', directory)
        io.dump(directory/'independent_audit.json', result)
        results.append(dict(shot_id=sid, thread_id=ids[0], usage=usage, geometry=result))
    assert len(set(contexts)) == len(set(threads)) == 2
    result = dict(status='pass', contexts=contexts, results=results,
                  checks=['two distinct fresh thread IDs and temporary working directories',
                          'six hash-matched own-shot image attachments per call',
                          'no other shot in prompt; no old verdict input',
                          'ephemeral and disabled tools, project documents, memory and skills',
                          'tool-free native events and successful completion',
                          'independent single-shot graph coverage and geometry replay'])
    io.dump(root/'isolation_audit.json', result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path)
    run(parser.parse_args().root)
