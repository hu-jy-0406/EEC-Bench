"""Recorded-cut segmentation of single-video episodes and the guards that require it; no GPU or API calls."""
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import episode_shot_segments as seg
import run_vl_vv_pipeline as pipeline

spec = importlib.util.spec_from_file_location('prepare_case', ROOT / 'experiments/vl_vv_multimodel_first200_20260926/prepare_case.py')
prepare_case = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare_case)


def cut(start, visible, strength):
    return dict(recorded_start=start, visible_start=visible, offset=visible - start, strength=strength)


class RecordedCuts(unittest.TestCase):
    def test_cinetrans_latents_map_to_frames(self):
        with tempfile.TemporaryDirectory() as t:
            up = Path(t)
            (up / 'metadata.json').write_text(json.dumps({'mask': {'mask_info': [21, 20, 20, 20]}}))
            rec = seg.recorded_shot_starts('cinetrans', up / 'video.mp4', up)
            self.assertEqual((rec['starts'], rec['frames']), ([0, 81, 161, 241], 321))

    def test_holocine_cuts_and_video_hash(self):
        with tempfile.TemporaryDirectory() as t:
            up = Path(t)
            video = up / 'episode.mp4'
            video.write_bytes(b'video bytes')
            attempt = up / 'attempt'
            attempt.mkdir()
            (attempt / 'input.json').write_text(json.dumps({'cuts': [81, 161], 'frames': 241}))
            (up / 'result.json').write_text(json.dumps({'attempt': str(attempt), 'video_sha256': hashlib.sha256(b'video bytes').hexdigest()}))
            rec = seg.recorded_shot_starts('holocine', video, up)
            self.assertEqual((rec['starts'], rec['frames']), ([0, 81, 161], 241))
            video.write_bytes(b'different video')
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                seg.recorded_shot_starts('holocine', video, up)

    def test_unknown_model_and_missing_record_are_errors(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(ValueError, 'No recorded-cut segmentation'):
                seg.recorded_shot_starts('wan21', Path(t) / 'v.mp4', t)
            with self.assertRaisesRegex(ValueError, 'No CineTrans inference record'):
                seg.recorded_shot_starts('cinetrans', Path(t) / 'v.mp4', t)


class KeyframePlan(unittest.TestCase):
    def test_four_shot_plan(self):
        cuts = [cut(81, 84, 20), cut(161, 164, 20), cut(241, 244, 20)]
        plan = seg.keyframe_plan([0, 81, 161, 241], 321, cuts, 1.0)
        self.assertEqual([p['keyframe_indices'] for p in plan],
                         [[0, 15, 30, 46, 61, 76], [85, 99, 113, 128, 142, 156],
                          [165, 179, 193, 208, 222, 236], [245, 259, 273, 288, 302, 316]])

    def test_clear_late_cut_moves_the_first_keyframe_but_noise_does_not(self):
        late = seg.keyframe_plan([0, 81], 161, [cut(81, 88, 17.1)], 3.6)
        self.assertEqual(late[1]['keyframe_indices'][0], 89)
        noise = seg.keyframe_plan([0, 81], 161, [cut(81, 89, 10.7)], 0.06)
        self.assertEqual(noise[1]['keyframe_indices'][0], 85)


class Guards(unittest.TestCase):
    def manifests(self):
        frames = [dict(frame_id=i) for i in range(6)]
        clip = {'shots': [{'shot_id': 'Shot1', 'source_scope': 'shot', 'frames': frames}]}
        legacy = {'shots': [{'shot_id': 'Shot1', 'source_scope': 'episode', 'frames': frames}]}
        recorded = {'segmentation': {'source': seg.SEGMENTATION_SOURCE},
                    'shots': [{'shot_id': 'Shot1', 'source_scope': 'episode', 'segment_start_frame': 0,
                               'frames': [dict(frame_id=i, frame_index=i) for i in range(6)]}]}
        return clip, legacy, recorded

    def test_only_legacy_episode_manifests_are_rejected(self):
        clip, legacy, recorded = self.manifests()
        self.assertTrue(seg.is_record_segmented(clip))
        self.assertTrue(seg.is_record_segmented(recorded))
        self.assertFalse(seg.is_record_segmented(legacy))
        with self.assertRaisesRegex(ValueError, 'nominal 5 s grid'):
            seg.require_record_segmentation(legacy)
        seg.require_record_segmentation(legacy, allow_legacy=True)

    def test_pipeline_rejects_legacy_case_unless_flagged_and_passes_the_flag(self):
        _, legacy, _ = self.manifests()
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            case = root / 'case'
            case.mkdir()
            frames = []
            for i in range(6):
                f = root / f'f{i}.jpg'
                f.write_bytes(b'x')
                frames.append(dict(frame_id=i, path=str(f)))
            legacy['shots'][0]['frames'] = frames
            (case / 'raw_manifest.json').write_text(json.dumps(legacy))
            (case / 'contract.json').write_text('{}')
            (case / 'run.json').write_text(json.dumps(dict(protocol='vl_vv_detection_v1', status='complete')))
            (case / 'episode_entities.json').write_text(json.dumps(dict(protocol='vl_vv_detection_v1', status='matched')))
            with self.assertRaisesRegex(ValueError, 'nominal 5 s grid'):
                pipeline.build_plan(case, root / 'run', 'from-registry', allow_v1_contract=True)
            plan = pipeline.build_plan(case, root / 'run', 'from-registry', allow_legacy_keyframes=True, allow_v1_contract=True)
            self.assertIn('--allow-legacy-nominal-keyframes', plan['stages'][0]['command'])
            self.assertIn('--allow-legacy-nominal-keyframes', plan['stages'][1]['command'])


class PrepareCaseEpisode(unittest.TestCase):
    def test_recorded_cut_shots_extracts_planned_frames_from_a_real_video(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            video = root / 'video.mp4'
            subprocess.run([seg.ffmpeg(), '-v', 'error', '-f', 'lavfi', '-i', 'testsrc=size=64x48:rate=16', '-frames:v', '161',
                            '-pix_fmt', 'yuv420p', str(video)], check=True)
            (root / 'metadata.json').write_text(json.dumps({'mask': {'mask_info': [21, 20]}}))
            task = dict(task_id='t', model_id='cinetrans', shots=[
                dict(shot_id='Shot1', source_video=str(video), source_bytes=video.stat().st_size, source={'upstream_path': str(root)},
                     target_duration_seconds=5, episode_offset_sec=0.0),
                dict(shot_id='Shot2', source_video=str(video), source_bytes=video.stat().st_size, source={'upstream_path': str(root)},
                     target_duration_seconds=5, episode_offset_sec=5.0)])
            ffmpeg, ffprobe, imageio_ffmpeg = prepare_case.media_tools()
            shots, segmentation, _, _ = prepare_case.recorded_cut_shots(task, root / 'frames', ffprobe, imageio_ffmpeg)
            self.assertEqual(segmentation['shot_starts'], [0, 81])
            self.assertEqual([f['frame_index'] for f in shots[1]['frames']], [85, 99, 113, 128, 142, 156])
            self.assertEqual(shots[1]['segment_start_frame'], 81)
            self.assertTrue(all(Path(f['path']).is_file() for s in shots for f in s['frames']))
            self.assertTrue(seg.is_record_segmented(dict(segmentation=segmentation, shots=shots)))


if __name__ == '__main__':
    unittest.main()
