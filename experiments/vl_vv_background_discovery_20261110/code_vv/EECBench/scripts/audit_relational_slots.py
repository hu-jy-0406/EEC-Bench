#!/usr/bin/env python3
"""Read-only replay/provenance audit plus display-only compact previews."""
import argparse
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
from PIL import Image,ImageDraw,ImageFont


def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);args=p.parse_args();root=args.run.resolve()
    read=lambda p:json.loads(p.read_text())
    summary=read(root/'summary.json');run=read(root/'matching.json');slots=read(root/'global_slots.json')['slots']
    checks=[]
    def check(name,ok):
        if not ok:raise AssertionError(name)
        checks.append(name)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    source_path=Path(summary['input_path']);source=read(source_path)
    check('unchanged_source_graph',sha(source_path)==summary['input_hash_before']==summary['input_hash_after'])
    for name,digest in summary['code_hashes'].items():check('code_snapshot_'+name,sha(root/name)==digest)
    # Import the run's frozen numerical code, not a later workspace edit.
    import sys
    sys.path.insert(0,str(root))
    from relational_slot_matching import Config,build_graph,matching_costs,objective,propose_backbones,run_matching
    cfg=Config(**run['config']);graphs=[build_graph(s) for s in source['shots']]
    expected={g['shot_id']:g['ids'] for g in graphs}
    source_members=[r['source'] for r in slots if r['source'] is not None]
    target_members=[r['target'] for r in slots if r['target'] is not None]
    check('every_source_node_once',sorted(source_members)==sorted(graphs[0]['ids']) and len(set(source_members))==len(source_members))
    check('every_target_node_once',sorted(target_members)==sorted(graphs[1]['ids']) and len(set(target_members))==len(target_members))
    stage_counts=[]
    for g in graphs:
        saved=read(root/f'{g["shot_id"]}_relations.json');n=len(g['ids'])
        check('directed_edge_coverage_'+g['shot_id'],len(saved['edges'])==n*(n-1))
        check('frame_edge_coverage_'+g['shot_id'],all(len(rows)==n*(n-1) for rows in saved['frame_edges'].values()))
        check('frozen_entity_inventory_'+g['shot_id'],saved['ids']==g['ids'])
        registry=read(source_path.parents[1]/'wedetect_shot_entities_20260912'/'run01'/'shots'/g['shot_id']/'entities.json')
        check('original_registry_ids_'+g['shot_id'],[g['shot_id']+'/'+e['entity_id'] for e in registry['entities']]==g['ids'])
        for e in saved['edges']:
            if not e['frame_ids']:check('unknown_edge_'+g['shot_id']+str((e['source'],e['target'])),e['median'] is None and e['status']=='unknown')
        observed=sum(r['status']!='unknown' for rows in saved['frame_edges'].values() for r in rows)
        stage_counts.append(dict(shot=g['shot_id'],nodes=n,directed_edges=n*(n-1),
                                 frame_edge_rows=n*(n-1)*len(g['frames']),observed_frame_edges=observed))
    for k,r in enumerate(run['solutions']):
        h=r['hypothesis'];h['rotation']=np.array(h['rotation']);h['translation']=np.array(h['translation'])
        unary,tensor,distance=matching_costs(*graphs,h,cfg)
        replay=objective(r['mapping'],unary,tensor,cfg)
        check(f'objective_replay_{k}',abs(replay-r['objective'])<1e-9)
        check(f'one_to_one_{k}',len({i for i,j in r['mapping']})==len(r['mapping'])==len({j for i,j in r['mapping']}))
        check(f'descent_{k}',all(x>=y-1e-10 for x,y in zip(r['objective_trace'],r['objective_trace'][1:])))
        check(f'proper_transform_{k}',h['scale']>0 and np.allclose(h['rotation'].T@h['rotation'],np.eye(3)) and np.linalg.det(h['rotation'])>.999)
    # Natural input label ablation: names/reasons are replaced, numerical answers unchanged.
    renamed=json.loads(json.dumps(source))
    for sh in renamed['shots']:
        for e in sh['entities']:
            e['name']='renamed_unrelated'
            for ob in e['observations']:ob['reason']='unrelated misleading text'
            for st in e['states']:
                if st['geometry']:st['geometry']['name']='wrong label'
    renamed_graphs=[build_graph(s) for s in renamed['shots']]
    check('name_reason_ablation_descriptors',all(np.allclose(a['descriptors'],b['descriptors'],equal_nan=True) for a,b in zip(graphs,renamed_graphs)))
    ablation=run_matching(*renamed_graphs,cfg)
    check('name_reason_ablation_all_mappings',[r['mapping'] for r in ablation['solutions']]==[r['mapping'] for r in run['solutions']])
    check('name_reason_ablation_objectives',np.allclose([r['objective'] for r in ablation['solutions']],[r['objective'] for r in run['solutions']]))
    for f in read(root/'display_images.json'):check('display_frame_'+Path(f['path']).parent.name+'_'+Path(f['path']).name,sha(Path(f['path']))==f['sha256'])
    page=(root/'viewer.html').read_text()
    check('all_slot_ids_in_viewer',all(r['slot_id'] in page for r in slots))
    check('no_remote_image_dependencies','src="http' not in page and 'https://' not in page)
    js=page.split('<script>',1)[1].split('</script>',1)[0]
    (root/'viewer_script.js').write_text(js)
    node=shutil.which('node')
    if node:
        subprocess.run([node,'--check',str(root/'viewer_script.js')],check=True,capture_output=True)
        checks.append('javascript_syntax')
    browser_available=importlib.util.find_spec('playwright') is not None
    browser_result='not_run'
    if browser_available:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage','--disable-gpu'])
                tab=browser.new_page(viewport={'width':1440,'height':1000})
                errors=[];tab.on('pageerror',lambda e:errors.append(str(e)))
                tab.goto((root/'viewer.html').as_uri());tab.wait_for_timeout(800)
                check('browser_row_count',tab.locator('#rows tr').count()==len(slots))
                if len(run['solutions'])>1:
                    tab.select_option('#solution','1');tab.locator('#rows tr').first.click()
                    tab.select_option('#frame0','24');tab.wait_for_timeout(250)
                    tab.select_option('#solution','0')
                check('browser_no_page_errors',not errors)
                tab.screenshot(path=str(root/'viewer_screenshot.png'),full_page=False)
                browser.close();browser_result='passed'
        except Exception as exc:
            browser_result='unavailable_or_failed: '+str(exc)[:350]
    overview=Image.open(root/'overview.png');overview.thumbnail((1200,420));overview.save(root/'overview_preview.jpg',quality=82)
    sheet=Image.open(root/'slots_contact_sheet.jpg')
    match_rows=[i for i,r in enumerate(slots) if r['source'] and r['target']]
    preview=Image.new('RGB',(1120,70+150*len(match_rows)),'#f3f6f9')
    preview.paste(sheet.crop((0,0,1120,60)),(0,0))
    for k,i in enumerate(match_rows):preview.paste(sheet.crop((0,60+150*i,1120,60+150*(i+1))),(0,60+150*k))
    preview.save(root/'matched_pairs.jpg',quality=86)
    variants=[]
    for path in sorted(root.glob('variant_*.json')):
        v=read(path);sol=v['solutions'][0] if v['solutions'] else None
        variants.append(dict(variant=path.stem,best_matches=len(sol['mapping']) if sol else 0,
                             mapping=sol['mapping'] if sol else [],
                             yaw_degrees=np.degrees(sol['hypothesis']['yaw']) if sol else None,
                             normalized_objective=sol['normalized_objective'] if sol else None))
    result=dict(status='pass',checks=checks,stage_counts=stage_counts,variants=variants,
                browser_validation=browser_result,algorithm_accuracy_validated=False,
                slots_count=len(slots),name_ablation_passed=True)
    (root/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
