"""Deterministic unit and integration tests for Decision Intelligence."""

from app.core.config import DEFAULT_DECISION_WEIGHTS
from app.core.v11_config import ScannerProfileConfig, ScannerProfileName
from app.engine.decision import DecisionEngine
from app.models.decision import DecisionAction, DecisionGrade
from app.models.facts import Facts
from app.models.market import (
    MarketBreadth,
    MarketProfile,
    MarketRegime,
    MarketVolatility,
)
from app.models.risk import RiskGrade
from app.models.sector import SectorFacts, SectorProfile, SectorRotation
from app.models.setup import SetupType
from tests.test_scanner_report import build_test_scanner


def _market(state: MarketRegime, score: float, confidence: float = 1) -> MarketProfile:
    """Build a minimal complete market profile for decision tests."""
    return MarketProfile(
        score=score,
        confidence=confidence,
        state=state,
        reasons=(f"{state.value} market",),
        indexes={},
        breadth=MarketBreadth(
            universe_size=100,
            advancers=70,
            decliners=30,
            unchanged=0,
            advance_decline_ratio=70 / 30,
            percentage_above_ema20=75,
            percentage_above_ema50=70,
            percentage_above_ema200=65,
            new_highs=10,
            new_lows=1,
        ),
        volatility=MarketVolatility(india_vix=13, atr_expansion=0, gap_frequency=0.02),
    )


def _sector(
    score: float = 95,
    rotation: SectorRotation = SectorRotation.LEADING,
) -> SectorProfile:
    """Build a representative ranked sector profile."""
    facts = SectorFacts(
        name="Defence",
        member_count=20,
        return_5d=0.04,
        return_10d=0.06,
        return_20d=0.08,
        return_50d=0.15,
        return_100d=0.25,
        return_150d=0.35,
        return_250d=0.50,
        relative_strength_vs_nifty=0.20,
        average_member_relative_strength=90,
        percentage_above_ema20=90,
        percentage_above_ema50=92,
        percentage_above_ema200=85,
        new_high_percentage=20,
        new_low_percentage=0,
        average_volume_ratio=1.2,
        momentum_score=85,
    )
    return SectorProfile(
        score=score,
        confidence=1,
        rank=1,
        percentile=99,
        rotation=rotation,
        reasons=("Broad participation",),
        facts=facts,
    )


def _evaluate(
    facts: Facts,
    market: MarketProfile,
    sector: SectorProfile | None = None,
):
    """Evaluate the shared profiles with optional targeted market and sector."""
    return DecisionEngine().evaluate(
        market,
        sector or _sector(),
        facts.rs_profile,
        facts.stock_profile,
        facts.setup_profile,
        facts.risk_profile,
        facts.breadth_profile,
        facts.cpr_profile,
    )


def test_healthy_bull_produces_buy_with_explanations(bullish_facts: Facts) -> None:
    """Strong aligned intelligence in a healthy bull should produce BUY."""
    profile = _evaluate(bullish_facts, _market(MarketRegime.HEALTHY_BULL, 100))
    assert profile.action == DecisionAction.BUY
    assert profile.grade in {DecisionGrade.A_PLUS, DecisionGrade.A}
    assert profile.confidence >= 0.95
    assert "Healthy Bull market" in profile.reasons
    assert "Leading Defence sector" in profile.reasons
    assert "Perfect EMA alignment" in profile.reasons
    assert any("R available" in reason for reason in profile.reasons)


def test_range_is_watchlist_and_bear_is_avoid(bullish_facts: Facts) -> None:
    """Identical stock evidence should change action with the market regime."""
    ranged = _evaluate(bullish_facts, _market(MarketRegime.RANGE, 55))
    bearish = _evaluate(bullish_facts, _market(MarketRegime.BEAR, 25))
    assert ranged.action == DecisionAction.WATCHLIST
    assert bearish.action == DecisionAction.AVOID
    assert bearish.grade == DecisionGrade.REJECT


def test_weak_setup_and_poor_risk_reject(bullish_facts: Facts) -> None:
    """Setup and risk gates should override otherwise strong component scores."""
    weak_setup = bullish_facts.setup_profile.model_copy(
        update={"score": 30, "best_setup_type": SetupType.NONE}
    )
    poor_risk = bullish_facts.risk_profile.model_copy(
        update={"score": 30, "grade": RiskGrade.REJECT}
    )
    engine = DecisionEngine()
    inputs = (
        _market(MarketRegime.HEALTHY_BULL, 100),
        _sector(),
        bullish_facts.rs_profile,
        bullish_facts.stock_profile,
    )
    setup_reject = engine.evaluate(*inputs, weak_setup, bullish_facts.risk_profile)
    risk_reject = engine.evaluate(*inputs, bullish_facts.setup_profile, poor_risk)
    assert setup_reject.action == DecisionAction.AVOID
    assert risk_reject.action == DecisionAction.AVOID


def test_missing_data_reduces_confidence_and_warns() -> None:
    """Missing profiles should be explicit and must not produce a decision score."""
    profile = DecisionEngine().evaluate(None, None, None, None, None, None)
    assert profile.action == DecisionAction.AVOID
    assert profile.confidence == 0
    assert profile.decision_score == 0
    assert any("Missing intelligence" in warning for warning in profile.warnings)
    assert any("Range weights" in warning for warning in profile.warnings)


def test_weights_adapt_to_regime_and_remain_normalized(bullish_facts: Facts) -> None:
    """Market, setup, and sector contributions should use configured regime weights."""
    healthy = _evaluate(bullish_facts, _market(MarketRegime.HEALTHY_BULL, 100))
    ranged = _evaluate(bullish_facts, _market(MarketRegime.RANGE, 55))
    bearish = _evaluate(bullish_facts, _market(MarketRegime.BEAR, 25))
    assert healthy.weight_breakdown["market"].weight == 0.15
    assert ranged.weight_breakdown["market"].weight == 0.25
    assert bearish.weight_breakdown["market"].weight == 0.30
    assert ranged.weight_breakdown["setup"].weight > healthy.weight_breakdown["setup"].weight
    for weights in DEFAULT_DECISION_WEIGHTS.values():
        assert sum(weights.model_dump().values()) == 1


def test_scanner_attaches_decision_and_ranks_by_decision_score(rising_frame) -> None:
    """Scanner results should serialize decisions and rank on their adaptive scores."""
    results = build_test_scanner(rising_frame).scan(["WEAK", "STRONG"])
    assert all(result.decision_profile is not None for result in results)
    assert results[0].decision_score >= results[1].decision_score
    assert [result.rank for result in results] == [1, 2]


def test_scanner_profile_gates_change_buy_eligibility(bullish_facts: Facts) -> None:
    """The same weighted candidate receives different actions under distinct policies."""
    engine = DecisionEngine()
    inputs = (
        _market(MarketRegime.HEALTHY_BULL, 100),
        _sector(),
        bullish_facts.rs_profile,
        bullish_facts.stock_profile,
        bullish_facts.setup_profile,
        bullish_facts.risk_profile,
        bullish_facts.breadth_profile,
        bullish_facts.cpr_profile,
        bullish_facts.avwap_profile,
        None,
        bullish_facts.volume_profile,
    )
    default = engine.evaluate(
        *inputs,
        ScannerProfileConfig(name=ScannerProfileName.MOMENTUM_BREAKOUT),
    )
    ipo = engine.evaluate(
        *inputs,
        ScannerProfileConfig(name=ScannerProfileName.IPO_LEADER),
    )
    assert default.action == DecisionAction.BUY
    assert ipo.action == DecisionAction.WATCHLIST
    assert any("not eligible" in warning for warning in ipo.warnings)
