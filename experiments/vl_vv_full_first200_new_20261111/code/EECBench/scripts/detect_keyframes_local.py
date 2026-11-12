#!/usr/bin/env python3
"""Prompt-free YOLOE / Florence-2 OD on frozen shot manifests.

Only pixels (and the fixed Florence task token) reach the models. Input
registries are never loaded. Each detection is frame-local, not a track ID.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
import random
from pathlib import Path
import socket
import time


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', choices=['yoloe', 'florence'], required=True)
    p.add_argument('--input-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--weights', required=True)
    p.add_argument('--device', default='cuda:0')
    p.add_argument('--conf', type=float, default=0.25)
    p.add_argument('--imgsz', type=int, default=640)
    p.add_argument('--iou', type=float, default=0.7)
    p.add_argument('--max-det', type=int, default=300)
    p.add_argument('--max-new-tokens', type=int, default=2048)
    p.add_argument('--seed', type=int, default=0)
    args = p.parse_args()
    import numpy as np
    import torch
    from PIL import Image, ImageDraw, ImageFont
    torch.set_num_threads(2)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    frames = []
    manifests = sorted(args.input_root.glob('*/input_bundle/shot_manifest.json'))
    if not manifests:
        raise ValueError('No shot manifests found')
    for mp in manifests:
        m = json.loads(mp.read_text())
        for r in m['reference_frames']:
            path = mp.parent / Path(r['path']).name
            actual = sha(path)
            if actual != r['sha256']:
                raise ValueError(f'Input hash mismatch: {path}')
            frames.append(dict(shot=m['shot_id'], frame_id=r['frame_id'],
                               timestamp_sec=r['timestamp_sec'], path=str(path.resolve()), sha256=actual))
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / 'run.json').exists():
        raise FileExistsError('Use a fresh output directory; existing runs are immutable')
    weights = Path(args.weights).resolve()
    weight_hashes = {str(f.relative_to(weights)): sha(f) for f in sorted(weights.glob('*')) if f.is_file()} if weights.is_dir() else {weights.name: sha(weights)}
    run = dict(status='running', model=args.model, config={k: str(v) if isinstance(v, Path) else v for k,v in vars(args).items()},
               host=socket.gethostname(), pid=os.getpid(), start_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
               torch=torch.__version__, hip=torch.version.hip, device_name=torch.cuda.get_device_name(0) if args.device.startswith('cuda') else 'cpu',
               packages={k: importlib.metadata.version(k) for k in ['transformers','ultralytics','numpy','torchvision']},
               script_sha256=sha(__file__), weight_hashes=weight_hashes, frames=frames, results=[])
    dump(args.output / 'run.json', run)
    if args.model == 'yoloe':
        from ultralytics import YOLOE
        model = YOLOE(str(weights))
        dump(args.output / 'vocabulary.json', model.names)
    else:
        from transformers import AutoModelForCausalLM, AutoProcessor
        model = AutoModelForCausalLM.from_pretrained(str(weights), trust_remote_code=True,
                    torch_dtype=torch.float32, attn_implementation='eager', local_files_only=True).to(args.device).eval()
        processor = AutoProcessor.from_pretrained(str(weights), trust_remote_code=True, local_files_only=True)
    font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    font = ImageFont.truetype(font_path, 14) if Path(font_path).exists() else ImageFont.load_default()
    for frame in frames:
        start = time.monotonic()
        im = Image.open(frame['path']).convert('RGB')
        w,h = im.size
        out = args.output / frame['shot'] / f"frame_{frame['frame_id']:06d}"
        out.mkdir(parents=True, exist_ok=True)
        detections = []
        raw = None
        if args.model == 'yoloe':
            result = model.predict(im, device=args.device, imgsz=args.imgsz, conf=args.conf,
                                   iou=args.iou, max_det=args.max_det, retina_masks=True, verbose=False)[0]
            boxes = result.boxes.xyxy.cpu().tolist()
            scores = result.boxes.conf.cpu().tolist()
            classes = result.boxes.cls.int().cpu().tolist()
            for i,(box,score,cls) in enumerate(zip(boxes,scores,classes)):
                det = dict(id=i+1, label=result.names[cls], class_id=cls, box_xyxy=box, score=score)
                if result.masks is not None:
                    mask = (result.masks.data[i].cpu().numpy() > 0.5).astype(np.uint8) * 255
                    assert mask.shape == (h,w), (mask.shape, im.size)
                    mask_name = f'mask_{i+1:03d}.png'
                    Image.fromarray(mask).save(out / mask_name)
                    det['mask'] = mask_name
                detections.append(det)
        else:
            inputs = processor(text='<OD>', images=im, return_tensors='pt').to(args.device)
            with torch.inference_mode():
                ids = model.generate(input_ids=inputs['input_ids'], pixel_values=inputs['pixel_values'],
                        max_new_tokens=args.max_new_tokens, do_sample=False, num_beams=3)
            raw = processor.batch_decode(ids, skip_special_tokens=False)[0]
            parsed = processor.post_process_generation(raw, task='<OD>', image_size=(w,h))['<OD>']
            if len(parsed['bboxes']) != len(parsed['labels']):
                raise ValueError('Florence label/box mismatch')
            for i,(box,label) in enumerate(zip(parsed['bboxes'],parsed['labels'])):
                detections.append(dict(id=i+1,label=label,box_xyxy=box,score=None))
            (out / 'raw_generation.txt').write_text(raw)
            dump(out / 'generation.json', dict(token_count=int(ids.shape[-1]), max_new_tokens=args.max_new_tokens,
                   last_token=int(ids[0,-1]), eos_token_id=model.generation_config.eos_token_id,
                   potentially_truncated=bool(ids.shape[-1] >= args.max_new_tokens)))
        elapsed = time.monotonic()-start
        data = dict(**frame, image_size=[w,h], seconds=elapsed, detections=detections)
        dump(out / 'detections.json', data)
        canvas = im.copy()
        draw = ImageDraw.Draw(canvas)
        for d in detections:
            box = d['box_xyxy']
            color = tuple(int(x) for x in np.random.default_rng(d['id']).integers(60,230,3))
            draw.rectangle(box, outline=color, width=2)
            text = f"{d['id']} {d['label']}" + (f" {d['score']:.2f}" if d['score'] is not None else '')
            x,y = max(0,min(box[0],w-100)), max(0,box[1]-18)
            bb = draw.textbbox((x,y), text, font=font)
            draw.rectangle(bb, fill=(255,255,255))
            draw.text((x,y), text, fill=(0,0,0), font=font)
        canvas.save(out / 'boxes.jpg', quality=95)
        if args.model == 'yoloe' and detections:
            arr = np.array(im).astype(float)
            for d in detections:
                if 'mask' in d:
                    sel = np.array(Image.open(out / d['mask'])) > 0
                    color = np.random.default_rng(d['id']).integers(60,230,3)
                    arr[sel] = arr[sel]*0.55 + color*0.45
            Image.fromarray(arr.astype(np.uint8)).save(out / 'masks.jpg', quality=95)
        summary = dict(shot=frame['shot'],frame_id=frame['frame_id'],count=len(detections),
                       labels=[d['label'] for d in detections], seconds=elapsed,
                       result=str((out / 'detections.json').resolve()))
        run['results'].append(summary)
        dump(args.output / 'run.json', run)
        print(json.dumps(summary), flush=True)
    # Validate source bytes after the run as well.
    assert all(sha(f['path']) == f['sha256'] for f in frames)
    run['status']='success'
    run['end_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    dump(args.output / 'run.json', run)

if __name__ == '__main__':
    main()
