#!/usr/bin/env python3
"""Check six exported graphs, frozen partition, fusion accounting and camera glyphs."""
import argparse
from collections import Counter
import hashlib
from html.parser import HTMLParser
import itertools
import json
from pathlib import Path
import numpy as np
from run_isolated_shot_static_3d import owned_compute_job


def load(p):return json.loads(p.read_text())


class Page(HTMLParser):
    def __init__(self):super().__init__();self.plots=[];self.external=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='div' and 'plotly-graph-div' in attrs.get('class',''):self.plots.append(attrs['id'])
        if tag=='script' and 'src' in attrs:self.external.append(attrs['src'])


def run(root):
    owned_compute_job();methods=['codex','boxer_codex_camera','boxer_geocalib'];expectedplots=[];reports=[]
    camera_records={(r['method'],r['shot_id']):r for r in load(root/'camera_visualization.json')}
    labels=root.parents[1]/'shot_static_3d_isolated_20260914/run01'
    for method in methods:
        for sid in ['shot1','shot3']:
            expectedplots.append(method+'_'+sid)
            graph=load(root/method/sid/'Gs_global.json');frames=load(root/method/sid/'Gs_frames.json')['frames']
            review=load(labels/sid/'agent_review.json')['shots'][0]
            static={e['entity_id'] for e in review['entities'] if e['status']=='static'}
            assert len(graph['entities'])==len(static) and {e['entity_id'] for e in graph['entities']}==static
            assert [f['frame_id'] for f in frames]==graph['source_frame_ids']
            for frame in frames:assert {e['entity_id'] for e in frame['entities']}==static
            for provenance in graph['provenance']:
                assert hashlib.sha256(Path(provenance['path']).read_bytes()).hexdigest()==provenance['sha256']
            for c in graph['cameras']:
                r=np.array(c['R_world_from_camera']);assert np.allclose(r.T@r,np.eye(3),atol=1e-6) and np.linalg.det(r)>.99999
                np.testing.assert_allclose(r[:,2],c['forward_world'],atol=1e-8)
                np.testing.assert_allclose(-r[:,1],c['up_world'],atol=1e-8)
            for drawn in camera_records[(method,sid)]['cameras']:
                for fid in drawn['frame_ids']:
                    c=next(c for c in graph['cameras'] if c['frame_id']==fid)
                    np.testing.assert_allclose(drawn['position'],c['position_world'])
                    forward=np.array(drawn['forward_tip'])-drawn['position'];up=np.array(drawn['up_tip'])-drawn['position']
                    np.testing.assert_allclose(forward/np.linalg.norm(forward),c['forward_world'],atol=1e-8)
                    np.testing.assert_allclose(up/np.linalg.norm(up),c['up_world'],atol=1e-8)
                    assert np.dot(forward,up)<1e-7
            selected=outliers=0
            for e in graph['entities']:
                rows=e['frame_evidence'];used=[r for r in rows if r['selected']]
                for r,frame in zip(rows,frames):
                    copy=next(x for x in frame['entities'] if x['entity_id']==e['entity_id'])
                    assert copy['evidence']==r
                    if r['selected']:assert r['visible'] and r['eligible'] and r['weight']>0
                if not e['geometry']:assert not used;continue
                assert used and abs(sum(r['weight'] for r in used)-1)<1e-8
                groups=Counter(r['source_group'] for r in used)
                q=np.array([max(r['raw_quality'],1e-9)/groups[r['source_group']] for r in used]);q/=q.sum()
                np.testing.assert_allclose(q,[r['weight'] for r in used],atol=1e-12)
                assert len(groups)==e['aggregation']['distinct_geometry_sources']
                b=e['geometry'];size=np.array(b['size_xyz']);rot=np.array(b['R_world_from_object']);p=np.array(b['corners_world']);center=np.array(b['center_world'])
                assert min(size)>0 and np.isfinite(p).all() and p.shape==(8,3)
                np.testing.assert_allclose(rot.T@rot,np.eye(3),atol=1e-7);assert np.linalg.det(rot)>.99999
                expected=np.array(list(itertools.product((-1,1),repeat=3)))*size/2@rot.T+center
                np.testing.assert_allclose(p,expected,atol=1e-8)
                # Independent weighted-median necessary condition per coordinate.
                values=np.array([r['geometry']['center_world'] for r in used])
                for axis in range(3):
                    assert q[values[:,axis]<center[axis]-1e-8].sum()<=.5+1e-8
                    assert q[values[:,axis]>center[axis]+1e-8].sum()<=.5+1e-8
                selected+=len(used);outliers+=sum(r.get('reason')=='robust_center_outlier' for r in rows)
            reports.append(dict(method=method,shot_id=sid,entities=len(static),selected_observations=selected,center_outliers_rejected=outliers,counts=graph['counts']))
    page=Page();page.feed((root/'comparison.html').read_text());assert page.plots==expectedplots and not page.external
    result=dict(status='pass',graphs=reports,plot_order=page.plots,external_script_dependencies=page.external,
        checks=['identical frozen static partition in all three methods','six per-frame Gs per shot','source hashes','frame selection and shared-source weight normalization',
                'weighted center medians and proper rotations/eight corners','camera position and forward/up vectors incl rendered arrows','six offline plots in method rows and shot1-left/shot3-right order'],
        browser_runtime_validated=False,geometry_accuracy_validated=False)
    (root/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);run(p.parse_args().root)
