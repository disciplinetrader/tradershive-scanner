# Volume Intelligence Engine

The Volume Intelligence Engine evaluates institutional participation from normalized OHLCV
history. It combines multi-horizon relative volume, up/down-volume pressure, accumulation and
distribution sessions, contraction sequences, dry-up, expansion, churn, climax, reversal,
low-volume pullback, and pocket-pivot evidence.

`VolumeEngine.analyze(symbol, frame)` returns an immutable `VolumeProfile`. The profile contains
the overall quality score and grade, confidence, classified state, component scores, concrete
reasons, warnings, and the complete `VolumeFacts` snapshot. A minimum of 10 valid sessions is
required; confidence increases linearly to full confidence at 50 sessions.

The scanner calculates the profile once and stores it in `Facts`. `VolumeFeature` only exposes
that precomputed result to the existing scorer. API responses therefore include the complete
profile, while CLI and Excel outputs expose the volume grade, score, and state.

Run validation with `python -m pytest tests/test_volume_engine.py` and performance validation with
`python scripts/benchmark_volume_engine.py`.
