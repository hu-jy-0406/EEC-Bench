from pathlib import Path
r=Path(__file__).resolve().parent/'repos/StoryMem'
p=r/'pipeline.py';s=p.read_text();s=s.replace('import gc\n','import gc\nimport time\nimport json\n')
s=s.replace('frame_num=t2v_config.frame_num,','frame_num=args.frame_num or t2v_config.frame_num,').replace('frame_num=m2v_config.frame_num,','frame_num=args.frame_num or m2v_config.frame_num,')
s=s.replace('shift=t2v_config.sample_shift,','shift=args.sample_shift if args.sample_shift is not None else t2v_config.sample_shift,').replace('shift=m2v_config.sample_shift,','shift=args.sample_shift if args.sample_shift is not None else m2v_config.sample_shift,')
s=s.replace('sampling_steps=t2v_config.sample_steps,','sampling_steps=args.sample_steps or t2v_config.sample_steps,').replace('sampling_steps=m2v_config.sample_steps,','sampling_steps=args.sample_steps or m2v_config.sample_steps,')
s=s.replace('    ###### Init ######','    wall_start = time.monotonic()\n    ###### Init ######')
s=s.replace('        video = t2v_model.generate(', '        logging.info("TIMING t2v_init_seconds=%.6f", time.monotonic()-wall_start)\n        shot_start = time.monotonic()\n        video = t2v_model.generate(')
s=s.replace('        if rank == 0:\n            save_video(', '        torch.cuda.synchronize()\n        logging.info("TIMING t2v_generate_seconds=%.6f", time.monotonic()-shot_start)\n        if rank == 0:\n            save_video(',1)
s=s.replace('    for scene in story_script["scenes"]:', '    logging.info("TIMING m2v_init_seconds=%.6f", time.monotonic()-wall_start)\n    for scene in story_script["scenes"]:')
s=s.replace('            video = m2v_model.generate(', '            logging.info("MEMORY %s", json.dumps(memory_bank))\n            shot_start = time.monotonic()\n            video = m2v_model.generate(')
s=s.replace('            if rank == 0:\n                if first_frame_file', '            torch.cuda.synchronize()\n            logging.info("TIMING m2v_generate_seconds=%.6f scene=%s shot=%s memory_count=%s", time.monotonic()-shot_start, scene_num, shot_num, len(memory_bank))\n            if rank == 0:\n                if first_frame_file')
s=s.replace('videos = sorted(glob.glob(f"{args.output_dir}/*.mp4"))', 'videos = sorted(glob.glob(f"{args.output_dir}/[0-9][0-9]_[0-9][0-9].mp4"))')
p.write_text(s)
p=r/'extract_keyframes.py';s=p.read_text();s=s.replace('quality_model = HPSv3RewardInferencer(device="cuda")','quality_model = HPSv3RewardInferencer(config_path=os.environ.get("STORYMEM_HPS_CONFIG"), checkpoint_path=os.environ.get("STORYMEM_HPS_CHECKPOINT"), device="cuda")');s += '\n'
p.write_text(s)
p=r/'wan/memory2video.py';s=p.read_text();s=s.replace('os.path.join(finetune_high_noise_model_path, "backbone_high_noise.pth")','os.path.join(finetune_checkpoint_dir, "backbone_high_noise.pth")');p.write_text(s)
