#!/usr/bin/env python3
import json,pathlib,shutil,subprocess,sys,zipfile
HERE=pathlib.Path(__file__).resolve().parent
OLD=HERE.parent/'holocine_prompt_adaptation_20260922'
sys.path.insert(0,str(OLD));import run as old
old.io.safe_compute();a=old.read(HERE/'input_audit.json');assert a['status']=='pass'
limit=a['maximum_tokens'];out=HERE/'deliverables'
test=HERE.parent/'holocine_text1024_20260922/test_dynamic_context.py'
result=HERE/'dynamic_context_validation.json'
subprocess.run([sys.executable,str(test),'--text-len',str(limit),'--output',str(result),'--threads','1'],check=True)
assert old.read(result)['status']=='pass' and old.read(result)['target_text_len']==limit
shutil.copyfile(result,out/result.name);shutil.copyfile(HERE/'verify_bundle.py',out/'verify_bundle.py')
readme=f'''# HoloCine: unchanged shared Wan2.2/StoryMem prompts

This is the selected current input version. All400 global captions equal the current shared source/Wan global/StoryMem overview. All2,000 shot captions are byte-identical to the current effective Wan2.2 input and StoryMem video_prompts, including their previously audited context additions. No compression, alias rewriting or new wording is applied. HoloCine global/per-shot/shot-cut delimiters are the only formatting additions. Contracts, alignment contracts and entity schedules remain byte-preserved.

The largest complete native input is {limit} UMT5 tokens INCLUDING markers and EOS. All400 episodes use the same text_len={limit} and tokenizer.seq_len={limit}; the limit is measured from these inputs, not from earlier compressed candidates. The prior512 and compressed1024 packages are historical and are not the selected inputs.

After loading the official HoloCine pipeline, run:

    from text_context import configure_pipeline, generate_episode
    configure_pipeline(pipe)  # sets BOTH lengths to {limit}

Use generate_episode(pipe, native_prompt, expected_shots, **original_generation_kwargs), or call validate_prompt before invoking the configured pipe. Supply original validated frame counts, shot_cut_frames, resolution, sampler and seed. The adapter refuses truncation or mismatched shot counts. It does not load models, allocate resources, or start video generation on import. Feed exact raw text from holocine_input.json; do not use a structured helper that adds prose or concatenate contracts.

Validation: actual deployed tokenizer on all400, every shot's surviving token span, exact comparisons to both current model inputs, unchanged canonical contracts and schedules. Official T5/CrossAttention/mask code was also executed with tiny random CPU weights at512 and{limit} to check dynamic sequence shape and tail-token visibility. This does NOT establish full pretrained UMT5/14B video quality, ROCm kernel performance or memory use. Report the increased text budget as an explicit HoloCine evaluation setting; all400 use the same setting. No video generation was run.

Run python verify_bundle.py to verify this package's hashes, common-text provenance, native rendering, original contract prefixes, retained context additions, schedule/claim joins, and recorded length gates. It does not rerun tokenizer or generation. core100/priority200 are cumulative; the stage2/stage3 queues are incremental.
'''
(out/'README.md').write_text(readme)
hashes={str(p.relative_to(out)):old.sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='files.sha256.json'}
old.dump(out/'files.sha256.json',hashes)
sys.path.insert(0,str(HERE))
from verify_bundle import verify
v=verify(out)
archive=HERE/'holocine_shared_prompts_contracts_400.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in sorted(out.rglob('*')):
        if p.is_file():z.write(p,'holocine_inputs/'+str(p.relative_to(out)))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
v.update(archive=str(archive),archive_bytes=archive.stat().st_size,archive_sha256=old.sha(archive),new_api_calls=0,new_billable_api_tokens=0,new_api_usd=0)
old.dump(HERE/'package_validation.json',v)
report=f'''# HoloCine改用Wan2.2 / StoryMem共用未压缩输入

用户明确选择：用压缩前、与Wan2.2和StoryMem一致的prompt；按实际最大token数设置默认上限。

完成400episodes / 2,000shots。每条shot逐字等于当前Wan有效输入input_queue_400.v2.jsonl中的wan_prompt_en及StoryMem的video_prompts，包含既有已验证上下文补全；global逐字等于当前共同摘要。仅加入HoloCine原生分隔标记，没有压缩/重写/新别名。所有原始contract、alignment_contract、schedule及64,724claims保持不变。

完整episode实际UMT5长度：最短{a['minimum_tokens']}，最长{limit}，包括分隔标记与EOS。全400统一配置prompter.text_len={limit}、tokenizer.seq_len={limit}，所有输入完整、无截断、所有shot span保留。最长episode：{', '.join(a['longest_episode_ids'])}。按镜头数统计：{json.dumps(a['by_shot_count'],ensure_ascii=False)}。

以前报告的1215是更早source正文拼接的最大值，不包含Wan/StoryMem既有上下文补全；917属于压缩候选。它们都不作为本次共享输入的配置依据。较早241/159分组及1024压缩版方案保留为历史记录，本次全400均通过输入检查。

官方论文报告60秒/最多13镜头；已测官网13镜头演示prompt为425tokens，因此多shot本身不意味着超512。当前发布默认512是可配置预处理限制，官方未声明本次加长值的质量验证。模型T5相对位置、CrossAttention和shot mask沿实际sequence长度构造；真实官方代码tiny随机CPU权重的512/{limit}结构验证通过，含越过512/1024后的token可达性和对应shot隔离。共享checkout保持不变，由text_context.py在本次pipeline实例中显式配置两个长度。

没有运行预训练完整文本encoder/14B视频生成或画质对照；增加文本长度的实际GPU成本与生成质量尚待视频实验。不得把结构和tokenizer检查说成完整视频质量验证。实际模型权重、采样器、视频镜头参数均未改变或启动。

交付：holocine_shared_prompts_contracts_400.zip；deliverables/ready_queue.jsonl；profile.json；input_audit.json；dynamic_context_validation.json；package_validation.json。包内verify_bundle.py已通过完整读回哈希与合同映射校验。新增API调用0、计费API tokens0、API费用USD0（历史压缩费用独立保留）。

官方来源：https://arxiv.org/html/2510.20822v1#S4.SS1 ；https://github.com/yihao-meng/HoloCine#prompt-format ；https://holo-cine.github.io/ 。
'''
(HERE/'REPORT.md').write_text(report)
print(json.dumps(v),flush=True)
