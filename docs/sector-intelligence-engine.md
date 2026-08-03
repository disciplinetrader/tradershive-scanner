# Sector Intelligence Engine

The Sector Intelligence Engine identifies leadership, deterioration, and rotation from the same
normalized stock histories used by the scanner. It avoids hard-coded external index dependencies:
sector membership is explicit, versionable, and replaceable as index constituents change.

## Supported sectors

The default registry supports Banking, Financial Services, IT, Pharma, Auto, FMCG, Energy, Oil &
Gas, Metal, Realty, Infrastructure, Capital Goods, Defence, PSU, Chemical, and Consumption. Add a
`SectorDefinition` to configure another sector without changing engine calculations.

API scans accept an optional `sectors` object:

```json
{
  "symbols": ["HAL", "BEL", "TCS"],
  "sectors": {"HAL": "Defence", "BEL": "Defence", "TCS": "IT"}
}
```

The CLI accepts the same mapping from a JSON file:

```powershell
python main.py HAL BEL TCS --sector-map config/sectors.json
```

Symbols are normalized to `.NS`. Unsupported sectors and duplicate registry membership fail fast.
Unmapped stocks receive an explicit zero-confidence `Unclassified` profile, so missing metadata
does not penalize their scanner score.

## Methodology

Each represented sector aggregates equal-weight 5/10/20/50/100/150/250-session member returns,
weighted excess return versus NIFTY, member RS percentiles, EMA20/50/200 participation, new highs
and lows, volume ratio, and short/intermediate momentum.

Sector score weights cross-sector RS percentile at 35%, average member RS at 25%, breadth at 20%,
momentum at 15%, and breakout quality at 5%. Scores produce a zero-to-99 sector percentile and a
stable rank. Rotation uses short-versus-long relative acceleration:

- `Leading`: high rank with positive short- and long-term relative performance.
- `Improving`: positive short-term performance with meaningful acceleration.
- `Weakening`: established long-term leadership losing short-term strength.
- `Lagging`: no qualifying leadership or improvement.

`SectorFeature` contributes sector score using member-count confidence. `Facts` carries sector name,
rank, percentile, score, confidence, rotation, and reasons for every scanner result.

Run focused tests with `python -m pytest tests/test_sector_engine.py`.

