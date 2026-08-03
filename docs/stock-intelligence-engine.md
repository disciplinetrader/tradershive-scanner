# Stock Intelligence Engine

The Stock Intelligence Engine measures the intrinsic technical quality of each normalized OHLCV
history. It deliberately excludes chart-pattern and trade-setup detection.

`StockEngine.analyze(symbol, frame)` returns an immutable `StockProfile` containing trend,
momentum, participation, and health sub-scores. The overall score weights those dimensions at
35%, 30%, 20%, and 15%. Grades use stable thresholds: A+ (90+), A (80+), B (65+), C (50+), and D.

The engine requires at least 252 sessions. Confidence rises with history coverage and reaches 1.0
at 252 sessions. Scanner results expose `facts.stock_score`, `facts.stock_grade`, and the complete
`facts.stock_profile`; Excel and CLI outputs include the grade and score.

Structural counts compare daily highs and lows over the latest 20 sessions. ATR expansion compares
current ATR14 with its preceding 20-session mean. Volume expansion and contraction combine current
relative volume with recent-versus-baseline volume. Inside day, outside day, and NR7 are descriptive
bar facts only and do not constitute setup detection.
