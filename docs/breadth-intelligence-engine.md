# Breadth Intelligence Engine

The Breadth Intelligence Engine measures participation across the complete scanned universe. It
maintains a rolling advance/decline line and evaluates directional volume, new highs and lows,
moving-average participation, higher-high and higher-low participation, distribution clusters,
follow-through days, momentum, trend, and breadth thrust.

`BreadthEngine.analyze(frames)` returns one immutable `BreadthProfile` for the scan. The scanner
attaches that shared profile to every stock rather than recalculating it per symbol. The profile is
also an explicit input to Decision Intelligence and Situational Awareness.

Confidence reflects both valid universe coverage and available longitudinal history. Invalid
symbols are excluded, reduced coverage is disclosed, and a universe with no valid symbols fails
explicitly.

Run `python -m pytest tests/test_breadth_engine.py` for deterministic validation and
`python scripts/benchmark_breadth_engine.py` for the 1,000-stock performance gate.
