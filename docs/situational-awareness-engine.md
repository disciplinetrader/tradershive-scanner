# Situational Awareness Engine

The Situational Awareness Engine interprets existing Market, Sector, Relative Strength, Stock,
Setup, Risk, and Decision profiles. It does not calculate indicators and does not contribute to
stock scoring.

The Market regime establishes the initial trading bias and aggression. Existing breadth,
volatility, sector rotation, risk rejection, RS participation, and decision participation can only
reduce that posture. Bear and capitulation regimes force Cash mode with zero recommended open
positions and zero new risk per trade.

One immutable `SituationProfile` is produced per scan. It includes market health, risk environment,
money flow, Top and Bottom 5 sectors, improving and weakening sectors, preferred setup families,
relative position sizing, maximum positions, maximum risk per trade, holding-period guidance,
reasons, strategies, and warnings.

The same profile is attached to each API result for backward-compatible serialization. CLI output
prints it before the Top 20, and Excel output places a dedicated Situation Summary sheet first. Run
`python scripts/benchmark_situation_engine.py` for the 1,000-stock performance benchmark.
