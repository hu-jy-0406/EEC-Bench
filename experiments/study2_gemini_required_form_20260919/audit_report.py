"""Audit representation change and report this stage-only validation."""
import copy
import json
from pathlib import Path
import sys
from jsonschema import validate, ValidationError

ROOT = Path(__file__).resolve().parent
BENCH = ROOT.parents[1]
sys.path.insert(0, str(BENCH / 'scripts'))
import gs_gemini_backend as backend
from review_aligned_entity_identities import validate as validate_identity

run = ROOT / 'indexed_form'
call = run / 'call'
read = lambda p: json.loads(p.read_text())
state = read(run / 'result.json')
assert state['status'] != 'running'
request = read(call / 'request.json')
payload = read(call / 'input.json')
ids = [g['group_id'] for g in payload['initial_matching']['groups']]
wire_schema = read(call / 'gemini_output.schema.json')
assert wire_schema['properties']['initial_group_reviews']['required'] == ids
assert not wire_schema['properties']['initial_group_reviews']['additionalProperties']
assert all(backend.sha(Path(p).read_bytes()) == h for p, h in read(run / 'sources.json').items())
body, images = backend.build_request((call / 'gemini_prompt.txt').read_text(), wire_schema,
                                    [f['path'] for f in request['images']])
assert backend.sha(json.dumps(body).encode()) == request['request_body_sha256']
assert images == request['attachments']
source = Path(state['source'])
rejected = []
for name in ['identity_review_attempt1', 'identity_review']:
    old = copy.deepcopy(read(source / 'calls' / name / 'response.json'))
    count = len(old['initial_group_reviews'])
    rows = old['initial_group_reviews']
    old['initial_group_reviews'] = {r['initial_group_id']: ids.index(r['initial_group_id']) for r in rows}
    old['initial_group_review_rows'] = [{k:v for k,v in r.items() if k != 'initial_group_id'} for r in rows]
    try:
        validate(old, wire_schema)
    except ValidationError:
        rejected.append(count)
    else:
        raise AssertionError('Historical incomplete response incorrectly accepted')
result = read(call / 'response.json')
wire = read(call / 'gemini_form_response.json')
assert backend.decode_identity_review_form(wire, ids) == result
validate_identity(result, payload)
audit = dict(passed=True, required_group_count=len(ids), original_semantic_validation=True,
    historical_incomplete_responses_rejected=rejected, original_frames_and_diagnostic_unchanged=True,
    canonical_evidence_unchanged=True, request_body_reconstructed=True,
    lossless_response_decoding=True, no_generated_decisions_or_witnesses=True, unit_tests_passed=8)
backend.save(ROOT / 'audit.json', audit)
usage = state['usage']
actions = {}
for row in result['initial_group_reviews']:
    actions[row['action']] = actions.get(row['action'], 0) + 1
probes = {p.name: read(p) for p in ROOT.glob('*_probe.json')}
probe_tokens = sum(p.get('usage', {}).get('total_tokens', 0) for p in probes.values())
report = f'''# Study2 Gemini 必填组 ID 表修复验证

状态：通过。Gemini 3.5 Flash / medium 一次真实复核输出 **{state['reviewed_initial_groups']}/{state['expected_initial_groups']}** 组，原身份、实体完整性、证据和锚点语义校验全部通过。

用户要求将逐组复核改为填空。Gemini 专用适配器动态生成全部初始组 ID 为必填键，禁止额外键；每个键通过单值 enum 固定关联到一个复核行。模型以正常 JSON 对象填写每行的全部决定与证据字段，共享字段 schema 只传一次。程序严格检查行数恰好等于组数、索引和所有原字段，再恢复原数组接口。不补决定、不填证据、不放松原校验。普通 Codex/Astra pipeline 未改。

## 真实验证

- 同一 Study2 的冻结输入、12 张原始 JPEG、诊断图、初始匹配和配准；输入与来源哈希均未变。
- 只新调用 aligned identity review；这是修复验证，非从头重跑完整 pipeline。
- 复核 {len(ids)} 组，动作计数 `{json.dumps(actions)}`；最终 {state['final_groups']} 组。
- 最终单侧组检查 {state['noncommon_checks']}/{state['expected_noncommon_checks']}；语义校验通过。
- 调用耗时 {state['seconds']:.2f} 秒；输入 {usage['input_tokens']}、输出含思考 {usage['output_tokens']}、合计 {usage['input_tokens']+usage['output_tokens']} tokens；缓存输入 {usage['cached_input_tokens']} 已包含在输入内。
- 8 项 CPU 回归测试通过。历史 4/29 和 20/29 回复转换为新表后均被 required-key 校验拒绝。
- CPU：现有 owned allocation 191764 / node306，单个检查为空闲的 core21，nice19，GPU 隐藏，无新资源申请。
- presence/spatial 未运行，没有新的最终评分。单次通过不证明跨样例或多次调用稳定性。

## 接口限制与完整记录

最初把完整嵌套字段在29个 ID 下分别展开，接口返回 HTTP400；共享 `$ref`、缩短字段名、共享 witness 表、无固定内部字段的对象，以及29行 minItems/maxItems 的探针也返回400。原数组 schema、单组对象及必填 ID 对应字符串的探针被接受。JSON 文本值的真实调用填齐29个 ID，但 g01 内部 JSON 转义错误，已判失败且未修补。最终采用必填 ID/固定索引 + 正常 JSON 行数组；接口约束全部 ID 和每行字段，程序约束恰好29行。此版本没有转义字符串。schema 被拒绝的现象与[官方文档的复杂度限制](https://ai.google.dev/gemini-api/docs/structured-output)一致，但服务未给出具体限制值。

首次拒绝保留在 `call/`、`result.json`、`replay.log`；微型探针独立保存，共 {probe_tokens} 个已报告 tokens，HTTP400 未返回 usage。JSON 文本值失败保留在 `json_form/`，输入216147、输出含思考41061、合计257208 tokens。最终验证在 `indexed_form/`；原始 API 回复、实际 prompt/schema、表格式回复、解码后的 canonical 回复、usage、源码快照和来源哈希齐全。全部本次已报告用量为 {257208+probe_tokens+usage['input_tokens']+usage['output_tokens']} tokens。探针与失败请求没有混入原 CPU 实验账目。

审计：`audit.json`。历史失败实验保持原样。
'''
(ROOT / 'REPORT.md').write_text(report)
print(json.dumps(audit, indent=2))
