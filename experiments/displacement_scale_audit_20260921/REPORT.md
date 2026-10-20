# Existing Study2/3/4 displacement and scale audit

Each expected-static entity: mean of all unordered valid raw center pair distances; shot baseline: equal-entity median of these means. Keep fusion-unselected raw observations; n<2 excluded.

No model calls, refitting, filtering changes or production modifications. Coordinates use a model metric prior, not ground-truth metric calibration.

| Study | Shot3 to Shot1 fitted scale | Shot1 displacement median | Shot2 displacement median | Shot3 displacement median |
|---|---:|---:|---:|---:|
| Study2 | 0.907475 | 0.040771 | 0.018827 | 0.060885 |
| Study3 | 0.776141 | 0.040779 | 0.013709 | 0.068833 |
| Study4 | 0.707850 | 0.034769 | 0.514551 | 0.096947 |

Displacement medians are in each original shot coordinate system; they mix scene scale, measurement variation and real displacement. They are NOT direct estimates of pure scale or calibrated noise. Shot2 is a separate scene; do not apply the Shot3 registration scale to Shot2.

The fitted scales are existing best-fit similarity parameters, not physical ground-truth scale ratios. Across independent episodes there is no shared known-size reference; entity sizes and scene extents are descriptive proxies confounded by scene content.

A common positive coordinate scaling multiplies every distance and its median by the same factor, so displacement/median is scale invariant when the denominator is positive. A numerical epsilon must scale with coordinates to preserve invariance when active. Pure scale invariance does not guarantee equal severity/calibrated thresholds across scenes.

Study4 Shot1 recomputation matches all previous entity means to <1e-12. No new inference or GPU work.
