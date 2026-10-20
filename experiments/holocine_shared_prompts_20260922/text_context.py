"""Explicit HoloCine text-context profile; keep the upstream checkout unchanged."""
import re

DEFAULT_TEXT_LEN = 1519

def configure_pipeline(pipe, text_len=DEFAULT_TEXT_LEN):
    if not isinstance(text_len, int) or text_len < 1:
        raise ValueError('text_len must be a positive integer')
    prompter = pipe.prompter
    before = dict(text_len=prompter.text_len, tokenizer_seq_len=prompter.tokenizer.seq_len)
    prompter.text_len = text_len
    prompter.tokenizer.seq_len = text_len
    assert prompter.text_len == prompter.tokenizer.seq_len == text_len
    return dict(profile='eec_holocine_shared_uncompressed_v1', previous=before, text_len=text_len,
                changes='Text sequence budget only; weights, prompt contents and shot settings unchanged.')

def validate_prompt(pipe, prompt, expected_shots):
    """Fail before diffusion if any text or shot is lost in the configured tokenizer."""
    t = pipe.prompter.tokenizer
    kw = dict(return_tensors=None, padding=False, return_mask=True,
              return_offsets_mapping=True, add_special_tokens=True)
    full = t(prompt, truncation=False, **kw)
    actual = t(prompt, **kw)
    ids, prod = full['input_ids'][0], actual['input_ids'][0]
    if ids != prod:
        raise ValueError(f'Text would be truncated: {len(ids)} tokens, limit {t.seq_len}')
    clean = t._clean(prompt)
    if len(re.findall(r'\[shot cut\]', clean)) + 1 != expected_shots:
        raise ValueError('Prompt shot count does not match contract mapping')
    marker = re.search(r'\[per shot caption\]', clean)
    if marker is None or '[global caption]' not in clean:
        raise ValueError('Native global/per-shot markers are required')
    starts = [marker.end()] + [m.end() for m in re.finditer(r'\[shot cut\]', clean)]
    ends = [m.start() for m in re.finditer(r'\[shot cut\]', clean)] + [len(clean)]
    spans = []
    for start, end in zip(starts, ends):
        indices = [i for i, (a,b) in enumerate(full['offset_mapping'])
                   if a != b and not (b <= start or a >= end)]
        if not indices:
            raise ValueError('Empty or missing shot caption')
        spans.append([min(indices), max(indices)+1])
    return dict(tokens=len(ids), limit=t.seq_len, untruncated=True, shots=len(spans),
                shot_caption_token_spans=spans)

def generate_episode(pipe, prompt, expected_shots, *, text_len=DEFAULT_TEXT_LEN, **generation_kwargs):
    """Use with a loaded official pipeline and separately chosen generation settings."""
    configure_pipeline(pipe, text_len)
    validate_prompt(pipe, prompt, expected_shots)
    cuts = generation_kwargs.get('shot_cut_frames')
    if cuts is None or len(cuts) != expected_shots-1:
        raise ValueError('Supply the separately validated original shot_cut_frames')
    if 'negative_prompt' in generation_kwargs:
        t=pipe.prompter.tokenizer
        full=t(generation_kwargs['negative_prompt'],return_tensors=None,padding=False,truncation=False)
        actual=t(generation_kwargs['negative_prompt'],return_tensors=None,padding=False)
        if full['input_ids'] != actual['input_ids']:
            raise ValueError('Negative prompt would be truncated')
    return pipe(prompt=prompt, **generation_kwargs)
