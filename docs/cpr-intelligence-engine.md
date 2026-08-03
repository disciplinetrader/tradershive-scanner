# CPR Intelligence Engine

The CPR Intelligence Engine calculates Central Pivot Range structure across daily, weekly, and
monthly timeframes. Each timeframe exposes pivot, top and bottom central levels, width and width
percentile, virgin status, price location, breakout distance, and its relationship to the previous
CPR.

`CPREngine.analyze(symbol, frame)` returns an immutable `CPRProfile` with expansion, trend
continuation, and range probabilities. Width classifications use each symbol and timeframe's own
historical distribution, making narrow and wide labels adaptive rather than fixed.

The scanner calculates CPR once per stock. The profile is exposed in Facts and API responses,
adaptively weighted by Decision Intelligence, summarized across the universe by Situational
Awareness, and included in CLI and Excel output.

Run `python -m pytest tests/test_cpr_engine.py` and `python scripts/benchmark_cpr_engine.py`.
