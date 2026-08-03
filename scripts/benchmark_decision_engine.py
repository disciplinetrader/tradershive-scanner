"""Deterministic 1,000-stock benchmark for the Decision Intelligence Engine."""

from time import perf_counter

from benchmark_risk_engine import build_facts_fixture

from app.engine.decision import DecisionEngine
from app.engine.risk import RiskEngine
from app.models.market import MarketProfile, MarketRegime
from app.models.risk import RiskGrade
from app.models.sector import SectorFacts, SectorProfile, SectorRotation

STOCK_COUNT = 1_000
CEILING_SECONDS = 5.0


def main() -> int:
    """Run decision aggregation and report throughput against the ceiling."""
    facts = build_facts_fixture()
    risk = RiskEngine().analyze(facts)
    risk = risk.model_copy(update={"score": 90, "grade": RiskGrade.A})
    market = MarketProfile.model_construct(
        score=95,
        confidence=1,
        state=MarketRegime.HEALTHY_BULL,
        reasons=("Healthy Bull market",),
        indexes={},
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
    engine = DecisionEngine()
    started = perf_counter()
    profiles = [
        engine.evaluate(
            market,
            sector,
            facts.rs_profile,
            facts.stock_profile,
            facts.setup_profile,
            risk,
        )
        for _ in range(STOCK_COUNT)
    ]
    elapsed = perf_counter() - started
    throughput = STOCK_COUNT / elapsed
    passed = len(profiles) == STOCK_COUNT and elapsed < CEILING_SECONDS
    print(f"Stocks: {len(profiles)}")
    print(f"Elapsed seconds: {elapsed:.3f}")
    print(f"Stocks per second: {throughput:.1f}")
    print(f"5-second ceiling: {'PASS' if passed else 'FAIL'}")
    example = profiles[0]
    print(
        f"Example: action={example.action.value}, grade={example.grade.value}, "
        f"score={example.decision_score:.2f}, confidence={example.confidence:.2f}"
    )
    ranked = []
    for index in range(20):
        stock = facts.stock_profile.model_copy(update={"score": max(55, 96 - index * 1.5)})
        setup = facts.setup_profile.model_copy(update={"score": max(45, 94 - index * 1.8)})
        candidate_risk = risk.model_copy(update={"score": max(50, 95 - index * 1.7)})
        percentile = max(30, 99 - index * 3)
        horizons = {
            name: getattr(facts.rs_profile, name).model_copy(update={"percentile": percentile})
            for name in ("rs5", "rs10", "rs20", "rs50", "rs100", "rs150", "rs250")
        }
        relative_strength = facts.rs_profile.model_copy(update=horizons)
        profile = engine.evaluate(
            market,
            sector,
            relative_strength,
            stock,
            setup,
            candidate_risk,
        )
        ranked.append((f"STOCK{index + 1:02d}.NS", profile))
    ranked.sort(key=lambda item: (-item[1].decision_score, item[0]))
    print("Top 20:")
    for rank, (symbol, profile) in enumerate(ranked, 1):
        print(
            f"{rank:>2} {symbol:<12} {profile.decision_score:>6.2f} "
            f"{profile.action.value:<9} {profile.grade.value:<6} {profile.confidence:>5.0%}"
        )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
