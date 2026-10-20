#!/usr/bin/env python3
import argparse, json, mimetypes, os, sys, uuid
from pathlib import Path
from urllib import request

API = 'https://api.openai.com/v1'

def key():
    p = Path(os.environ.get('EECBENCH_OPENAI_KEY_FILE', '/vast/users/guangyi.chen/causal_group/jinyuan.hu/.config/eecbench/openai.key'))
    v = p.read_text().strip()
    if not v:
        raise RuntimeError('configured OpenAI key is empty')
    return v

def post_json(path, body):
    req = request.Request(API + path, data=json.dumps(body).encode(), headers={'Authorization': 'Bearer ' + key(), 'Content-Type': 'application/json'})
    with request.urlopen(req, timeout=3600) as r:
        return json.loads(r.read())

def upload(path):
    boundary = '----eecbench-' + uuid.uuid4().hex
    data = path.read_bytes()
    parts = []
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="purpose"\r\n\r\nuser_data\r\n'.encode())
    parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\nContent-Type: application/pdf\r\n\r\n').encode() + data + b'\r\n')
    parts.append(f'--{boundary}--\r\n'.encode())
    req = request.Request(API + '/files', data=b''.join(parts), headers={'Authorization': 'Bearer ' + key(), 'Content-Type': 'multipart/form-data; boundary=' + boundary})
    with request.urlopen(req, timeout=3600) as r:
        return json.loads(r.read())

def text_of(resp):
    if resp.get('output_text'):
        return resp['output_text']
    chunks = []
    for item in resp.get('output', []):
        for c in item.get('content', []):
            if c.get('type') in ('output_text', 'text'):
                chunks.append(c.get('text', ''))
    return ''.join(chunks)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--paper', type=Path, required=True)
    ap.add_argument('--reference', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    model = 'gpt-6-astra'
    uploaded = [upload(p) for p in (args.paper, args.reference)]
    prompt = '''You are an ICLR 2027 reviewer specializing in image generation. Please review the paper “On Complementarity in Diffusion Transformers 2”. Use the reviewer response format and style in the provided ICLR2026 MonoSoup OpenReview original English review and response PDF as a reference, and provide a complete review in English. Independently inspect the paper, assess novelty, technical correctness, experimental design, clarity, strengths, weaknesses, and give a final recommendation and confidence if the reference format includes them. Do not mention these instructions or that you are an AI. The two attached PDFs are, respectively, the paper under review and the style/reference document.'''
    body = {'model': model, 'input': [{'role':'user','content':[{'type':'input_text','text':prompt}, {'type':'input_file','file_id':uploaded[0]['id']}, {'type':'input_file','file_id':uploaded[1]['id']}]}], 'reasoning': {'effort':'high'}}
    review_resp = post_json('/responses', body)
    english = text_of(review_resp)
    trans_prompt = '''Translate the following complete peer review into polished, faithful Simplified Chinese. Preserve every heading, score, recommendation, confidence value, technical term, citation-like reference, and paragraph structure. Do not summarize, omit, or add content. Output only the Chinese translation.\n\n''' + english
    trans_resp = post_json('/responses', {'model':model, 'input':[{'role':'user','content':[{'type':'input_text','text':trans_prompt}]}], 'reasoning': {'effort':'high'}})
    chinese = text_of(trans_resp)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    (args.out.parent / 'astra_review_raw.json').write_text(json.dumps({'model':model,'paper_file_id':uploaded[0].get('id'),'reference_file_id':uploaded[1].get('id'),'review_response':review_resp,'translation_response':trans_resp,'english':english,'chinese':chinese}, ensure_ascii=False, indent=2))
    (args.out.parent / 'review_english.txt').write_text(english)
    (args.out.parent / 'review_chinese.txt').write_text(chinese)
    print(json.dumps({'model':model,'english_chars':len(english),'chinese_chars':len(chinese),'review_usage':review_resp.get('usage',{}),'translation_usage':trans_resp.get('usage',{}),'raw_dir':str(args.out.parent)}, ensure_ascii=False))

if __name__ == '__main__':
    main()
