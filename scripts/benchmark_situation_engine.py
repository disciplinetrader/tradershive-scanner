"""Deterministic 1,000-stock benchmark for Situational Awareness."""

from time import perf_counter

from benchmark_risk_engine import build_facts_fixture

from app.engine.decision import DecisionEngine
from app.engine.risk import RiskEngine
from app.engine.situation import SituationEngine
from app.models.market import MarketBreadth, MarketProfile, MarketRegime, MarketVolatility
from app.models.risk import RiskGrade
from app.models.sector import SectorFacts, SectorProfile, SectorRotation

STOCK_COUNT = 1_000
CEILING_SECONDS = 5.0


def main() -> int:
    """Interpret 1,000 existing stock profiles and report elapsed time."""
    facts = build_facts_fixture()
    risk = RiskEngine().analyze(facts).model_copy(update={"score": 90, "grade": RiskGrade.A})
    market = MarketProfile(
        score=92,
        confidence=1,
        state=MarketRegime.HEALTHY_BULL,
        reasons=("Strong breadth", "Low VIX", "Broad market confirmation"),
        indexes={},
        breadth=MarketBreadth(
            universe_size=STOCK_COUNT,
            advancers=750,
            decliners=250,
            unchanged=0,
            advance_decline_ratio=3,
            percentage_above_ema20=78,
            percentage_above_ema50=72,
            percentage_above_ema200=68,
            new_highs=80,
            new_lows=5,
        ),
        volatility=MarketVolatility(india_vix=13, atr_expansion=0, gap_frequency=0.02),
    )
    sector = SectorProfile.model_construct(
        score=92,
        confidence=1,
        rank=1,
        percentile=99,
        rotation=SectorRotation.LEADING,
        reasons=("Broad participation",),
        facts=SectorFacts.model_construct(name="Defence"),
    )
    decision = DecisionEngine().evaluate(
        market,
        sector,
        facts.rs_profile,
        facts.stock_profile,
        facts.setup_profile,
        risk,
    )
    engine = SituationEngine()
    started = perf_counter()
    profile = engine.analyze(
        market,
        (sector,),
        (facts.rs_profile,) * STOCK_COUNT,
        (facts.stock_profile,) * STOCK_COUNT,
        (facts.setup_profile,) * STOCK_COUNT,
        (risk,) * STOCK_COUNT,
        (decision,) * STOCK_COUNT,
    )
    elapsed = perf_counter() - started
    throughput = STOCK_COUNT / elapsed
    passed = elapsed < CEILING_SECONDS
    print(f"Stocks: {STOCK_COUNT}")
    print(f"Elapsed seconds: {elapsed:.3f}")
    print(f"Stocks per second: {throughput:.1f}")
    print(f"5-second ceiling: {'PASS' if passed else 'FAIL'}")
    print(
        f"Example: regime={profile.market_regime.value}, bias={profile.trading_bias.value}, "
        f"aggression={profile.aggression.value}, money_flow={profile.money_flow.value}"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
