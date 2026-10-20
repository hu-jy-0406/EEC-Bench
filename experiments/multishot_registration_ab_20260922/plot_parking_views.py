"""Display frozen parking geometry; no model calls, refitting, or box edits."""
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from scipy.spatial import ConvexHull

ROOT = Path(__file__).resolve().parent
CASE = ROOT / 'shared/parking4'
OUT = CASE / 'display'
OUT.mkdir(exist_ok=True)
read = lambda p: json.loads(p.read_text())
graphs = {i: read(CASE / f'selected/Shot{i}_scene.json') for i in range(1, 5)}
colors = {1: '#1674be', 2: '#e4871b', 3: '#279b53', 4: '#9b51bc'}
names = {
    1: ['car', 'woman, green', 'woman, black', 'helmet'],
    2: ['woman, black', 'woman, green', 'mask', 'chain strap'],
    3: ['SUV', 'woman, green', 'woman, foreground', 'necklace', 'chain strap', 'held item*'],
    4: ['woman, green', 'woman, black', 'helmet', 'shoulder bag'],
}
plt.rcParams.update({'font.size': 11, 'axes.titleweight': 'bold', 'axes.spines.top': False,
                     'axes.spines.right': False, 'savefig.facecolor': 'white'})

def mapping(points, fit=None):
    p = np.asarray(points)
    return p if fit is None else fit['scale'] * p @ np.asarray(fit['rotation']).T + fit['translation']

def objects(i, fit=None):
    for e, name in zip(graphs[i]['entities'], names[i]):
        g = e.get('geometry')
        if g:
            yield e['entity_id'].split('/')[-1], name, mapping(g['corners_world'], fit), mapping(g['center_world'], fit)

def equal_limits(ax, pts, dim):
    p = np.asarray(pts)[:, :dim]
    lo, hi = p.min(0), p.max(0)
    mid = (lo + hi) / 2
    radius = max(float(np.max(hi - lo)) / 2 * 1.18, .15)
    ax.set_xlim(mid[0]-radius, mid[0]+radius)
    ax.set_ylim(mid[1]-radius, mid[1]+radius)
    if dim == 3:
        ax.set_zlim(mid[2]-radius, mid[2]+radius)
        ax.set_box_aspect((1, 1, 1))
    else:
        ax.set_aspect('equal', adjustable='box')

def top(ax, shots, fits=None, title=''):
    fits = fits or {}
    extent = []
    for i in shots:
        fit = fits.get(i)
        for eid, name, corners, center in objects(i, fit):
            p = corners[:, :2]
            hull = ConvexHull(p)
            poly = p[hull.vertices]
            ax.fill(poly[:,0], poly[:,1], color=colors[i], alpha=.06)
            poly = np.vstack([poly, poly[0]])
            ax.plot(poly[:,0], poly[:,1], color=colors[i], lw=1.7)
            ax.scatter(*center[:2], s=19, color=colors[i], zorder=4)
            ax.annotate(f'S{i}/{eid}', center[:2], xytext=(4, 5 if i != 3 else -12),
                        textcoords='offset points', fontsize=9, color=colors[i])
            extent.extend(p)
        cams = mapping([c['position_world'] for c in graphs[i]['cameras']], fit)
        ax.plot(cams[:,0], cams[:,1], ':', color=colors[i], lw=1)
        ax.scatter(*cams[0,:2], marker='^', color=colors[i], s=65)
        forward = np.asarray(graphs[i]['cameras'][0]['forward_world'])
        if fit:
            forward = np.asarray(fit['rotation']) @ forward
        direction = forward[:2] / max(np.linalg.norm(forward[:2]), 1e-12) * .22
        ax.annotate('', xy=cams[0,:2]+direction, xytext=cams[0,:2],
                    arrowprops=dict(arrowstyle='->', color=colors[i], lw=1.4))
        extent.extend(cams[:,:2])
    equal_limits(ax, extent, 2)
    ax.set_title(title, pad=12)
    ax.set_xlabel('X (model units)'); ax.set_ylabel('Y (model units)')
    ax.grid(alpha=.18)

fig = plt.figure(figsize=(14, 12))
for i in range(1,5):
    ax = fig.add_subplot(2,2,i, projection='3d')
    extent = []
    for eid, name, p, center in objects(i):
        for a in range(8):
            for bit in (1,2,4):
                b = a ^ bit
                if a < b:
                    ax.plot(*p[[a,b]].T, color=colors[i], alpha=.85, lw=1.3)
        ax.scatter(*center, color=colors[i], s=20)
        ax.text(*center, ' '+eid, color=colors[i], fontsize=10)
        extent.extend(p)
    cams = np.asarray([c['position_world'] for c in graphs[i]['cameras']])
    ax.plot(*cams.T, color=colors[i], ls=':', lw=1)
    ax.scatter(*cams[0], color=colors[i], marker='^', s=60)
    ax.text(*cams[0], ' C0', color=colors[i], fontsize=10)
    extent.extend(cams)
    equal_limits(ax, extent, 3)
    ax.set_xlabel('X'); ax.set_ylabel('Y'); ax.set_zlabel('Z (up)')
    ax.view_init(elev=24, azim=-62)
    ax.set_title(f'Shot {i}  |  independent coordinates', color=colors[i], pad=12)
    label = '   '.join(f'e{j+1}: {n}' for j,n in enumerate(names[i]))
    if i == 3:
        label = 'e1: SUV   e2: woman, green   e3: woman, foreground\ne4: necklace   e5: chain strap   e6: held item*'
    elif i in (1,2,4):
        label = '   '.join(f'e{j+1}: {n}' for j,n in enumerate(names[i][:2]))+'\n'+'   '.join(f'e{j+3}: {n}' for j,n in enumerate(names[i][2:]))
    ax.text2D(.5,-.07,label,transform=ax.transAxes,ha='center',fontsize=10)
fig.suptitle('Parking / four original 3D coordinate systems', fontsize=19, y=.985)
fig.text(.5,.015,'Frozen whole-shot representative boxes; all entities included. C0 = first camera. Separate model scales; not meters.\n*Shot3/e6 retains the original detector identity; short display label only.',ha='center',fontsize=11)
fig.subplots_adjust(left=.03,right=.97,top=.92,bottom=.11,wspace=.08,hspace=.26)
fig.savefig(OUT/'coordinates_3d.png',dpi=150); plt.close(fig)

fig, axes = plt.subplots(2,2,figsize=(13,12))
for i, ax in enumerate(axes.flat,1):
    top(ax,[i],title=f'Shot {i} / separate coordinate group')
fig.suptitle('Optimization result: all four shots remain unregistered', fontsize=18)
fig.text(.5,.02,'Top view along -Z; +Y upward, +X right. Triangles = first cameras. No cross-shot overlay is justified.',ha='center',fontsize=11)
fig.tight_layout(rect=[0,.05,1,.95]);fig.savefig(OUT/'optimization_top.png',dpi=150);plt.close(fig)

result = read(CASE/'direct/results.json')
fits={int(row['shot_id'][4:]):row['fit'] for row in result['shots']}
assert result['roots']==['Shot1','Shot2','Shot4']
fig=plt.figure(figsize=(17,7.5)); grid=fig.add_gridspec(1,3,width_ratios=[1.45,1,1])
for col, shots in enumerate(([1,3],[2],[4])):
    ax=fig.add_subplot(grid[0,col]); top(ax,shots,fits,title='Shot1 + Shot3 / Shot1 coordinates' if col==0 else f'Shot{shots[0]} / separate group')
fig.suptitle('Codex direct result: Shot3 mapped into Shot1; Shot2 and Shot4 separate',fontsize=18,y=.98)
fig.legend(handles=[Line2D([0],[0],color=colors[i],lw=3,label=f'Shot{i}') for i in range(1,5)],loc='upper center',bbox_to_anchor=(.5,.93),ncol=4,frameon=False)
fig.text(.5,.05,'Top view along -Z. Same original boxes as above; transformed only by the saved fit.\nShot3 -> Shot1: scale 0.68, yaw 160 deg, translation (-0.04, 0.55, -0.08). Low-confidence candidate; not validated accuracy.',ha='center',fontsize=11)
fig.subplots_adjust(top=.80,bottom=.15,left=.06,right=.98,wspace=.30)
fig.savefig(OUT/'codex_top.png',dpi=160);plt.close(fig)

selection=read(ROOT/'inputs/parking4/selection.json')
for row in selection['source_videos']:
    assert hashlib.sha256(Path(row['path']).read_bytes()).hexdigest()==row['sha256']
manifest=dict(shot_colors=colors,geometry='unchanged whole-shot representative corners_world',
              viewing_direction='top views look along negative Z with +Y up and +X right',
              videos=selection['source_videos'],figures=[str(p) for p in OUT.glob('*.png')],
              registration='original saved direct fit only; optimization has no fitted transforms',new_inference_calls=0)
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest,indent=2))
