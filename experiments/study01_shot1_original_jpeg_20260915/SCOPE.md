# Original JPEG controlled execution

User correction: use the exact JPEG files from the previous evaluation first; do not regenerate frames. The four-group PNG/width experiment was stopped and is excluded.

Two fresh independent Shot1 pipelines, six JPEGs each: WeDetect-Anything -> configured Codex within-shot clustering -> same GeoCalib/Boxer evidence generator -> fresh isolated Codex static/moving/unknown judgment. No Shot3, cross-shot relations or consistency scoring. All model and inference parameters are identical between groups. Detector: same process and CPU runtime, seed0, objectness0.1/NMS0.7/top100/class0.4. Codex: gpt-6-astra, medium, ephemeral contexts, same prompts, tools and history disabled. Each reviewer sees only its own shot and stage inputs.

Original dimensions remain852x480 and854x480; original compression/pixels also differ. This comparison controls execution environment and process, but does not isolate resolution alone. No original image is rewritten; CLI transport may make byte-identical temporary attachments. Source manifests and frame hashes are preserved in inputs.json.
