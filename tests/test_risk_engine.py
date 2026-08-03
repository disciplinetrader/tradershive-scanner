"""Unit, integration, and performance tests for Risk Intelligence."""

from time import perf_counter

import pytest

from app.engine.risk import RiskEngine
from app.models.facts import Facts
from app.models.risk import RiskGrade
from app.models.setup import SetupType
from tests.test_scanner_report import build_test_scanner


def _risk_facts(
    facts: Facts,
    *,
    entry: float | None = 100,
    stop: float | None = 95,
    objective_low: float = 75,
    high_52_week: float = 130,
) -> Facts:
    """Return facts with targeted structural prices for risk tests."""
    setup_facts = facts.setup_profile.facts.model_copy(
        update={
            "setup_type": SetupType.BREAKOUT_READY if entry is not None else SetupType.NONE,
            "pivot_price": entry,
            "invalidation_price": stop,
            "base_high": entry or 105,
            "base_low": objective_low,
        }
    )
    setup_profile = facts.setup_profile.model_copy(
        update={"best_setup_type": setup_facts.setup_type, "facts": setup_facts}
    )
    return facts.model_copy(
        update={
            "setup_profile": setup_profile,
            "setup_type": setup_facts.setup_type,
            "pivot_price": entry,
            "invalidation_price": stop,
            "high_52_week": high_52_week,
        }
    )


def test_valid_five_r_and_three_r_setups(bullish_facts: Facts) -> None:
    """True objective resistance should produce exact available R bands."""
    engine = RiskEngine()
    excellent = engine.analyze(_risk_facts(bullish_facts, objective_low=75))
    acceptable = engine.analyze(_risk_facts(bullish_facts, objective_low=85))
    assert excellent.facts.available_r_multiple == 5
    assert excellent.reward_score == 100
    assert excellent.grade != RiskGrade.REJECT
    assert acceptable.facts.available_r_multiple == 3
    assert acceptable.reward_score == 65


def test_below_two_r_is_rejected(bullish_facts: Facts) -> None:
    """Nearby objective resistance below 2R must reject the structure."""
    profile = RiskEngine().analyze(_risk_facts(bullish_facts, objective_low=96))
    assert profile.facts.available_r_multiple < 2
    assert profile.grade == RiskGrade.REJECT
    assert "Available reward is below 2R" in profile.warnings


def test_missing_invalidation_uses_structural_low(bullish_facts: Facts) -> None:
    """A missing explicit invalidation should fall back to the known base low."""
    profile = RiskEngine().analyze(_risk_facts(bullish_facts, stop=None, objective_low=95))
    assert profile.facts.stop_price == 95
    assert profile.facts.risk_per_share == 5


@pytest.mark.parametrize(
    ("stop", "warning"),
    [
        (101, "Stop is above or equal to entry"),
        (80, "Stop distance exceeds configured maximum"),
        (99.8, "Stop distance is unrealistically tight"),
    ],
)
def test_invalid_stop_structures_are_rejected(
    bullish_facts: Facts, stop: float, warning: str
) -> None:
    """Invalid, excessively wide, and excessively tight stops must reject."""
    profile = RiskEngine().analyze(_risk_facts(bullish_facts, stop=stop))
    assert profile.grade == RiskGrade.REJECT
    assert warning in profile.warnings


def test_extension_high_volatility_and_poor_liquidity_are_penalized(
    bullish_facts: Facts,
) -> None:
    """Extension, ATR, and turnover should independently reduce risk quality."""
    engine = RiskEngine()
    baseline_facts = _risk_facts(bullish_facts)
    baseline = engine.analyze(baseline_facts)
    extended = engine.analyze(baseline_facts.model_copy(update={"ema20": 80}))
    volatile = engine.analyze(baseline_facts.model_copy(update={"atr14": 12}))
    illiquid = engine.analyze(baseline_facts.model_copy(update={"average_volume": 100}))
    assert extended.extension_score < baseline.extension_score
    assert volatile.volatility_score < baseline.volatility_score
    assert illiquid.liquidity_score < 30
    assert illiquid.grade == RiskGrade.REJECT


@pytest.mark.parametrize(
    ("risk_percent", "expected_quantity"),
    [(0.25, 500), (0.50, 1_000), (1.00, 2_000)],
)
def test_position_sizing_standard_risk_budgets(risk_percent: float, expected_quantity: int) -> None:
    """Standard risk budgets should return deterministic integer quantities."""
    result = RiskEngine.position_size(1_000_000, risk_percent, 100, 95)
    assert result.quantity == expected_quantity
    assert result.actual_risk_percent == risk_percent


def test_position_sizing_rounds_down_and_handles_zero_quantity() -> None:
    """Sizing must floor fractional shares and safely return zero when necessary."""
    rounded = RiskEngine.position_size(100_000, 0.50, 101, 94)
    zero = RiskEngine.position_size(1_000, 0.25, 500, 400)
    assert rounded.quantity == 71
    assert rounded.position_value == 7_171
    assert zero.quantity == 0
    assert zero.actual_risk_percent == 0


def test_missing_resistance_reduces_confidence_without_fabricating_reward(
    bullish_facts: Facts,
) -> None:
    """Unknown resistance must leave R unavailable rather than assuming 5R."""
    base = _risk_facts(bullish_facts, objective_low=100, high_52_week=100)
    profile = RiskEngine().analyze(base)
    assert profile.facts.nearest_resistance is None
    assert profile.facts.available_r_multiple is None
    assert profile.confidence < base.setup_profile.confidence
    assert any("resistance is unavailable" in warning for warning in profile.warnings)


def test_invalid_and_incomplete_inputs_are_handled(bullish_facts: Facts) -> None:
    """Missing entry should reject, while invalid sizing inputs should fail clearly."""
    missing_entry = _risk_facts(bullish_facts, entry=None, stop=None)
    profile = RiskEngine().analyze(missing_entry)
    assert profile.grade == RiskGrade.REJECT
    assert profile.facts.entry_price is None
    with pytest.raises(ValueError, match="finite"):
        RiskEngine.position_size(float("nan"), 1, 100, 95)
    with pytest.raises(ValueError, match="greater than stop"):
        RiskEngine.position_size(100_000, 1, 95, 100)


def test_scanner_attaches_risk_profile(rising_frame) -> None:
    """Every scanner result should expose risk facts and a risk feature."""
    results = build_test_scanner(rising_frame).scan(["STRONG", "WEAK"])
    assert all(result.facts.risk_profile is not None for result in results)
    assert all(result.features["risk"].state == result.facts.risk_grade.value for result in results)


def test_risk_engine_profiles_one_thousand_stocks_within_budget(
    bullish_facts: Facts,
) -> None:
    """Pure risk calculation should scale across 1,000 stocks in five seconds."""
    engine = RiskEngine()
    facts = _risk_facts(bullish_facts)
    started = perf_counter()
    profiles = [engine.analyze(facts) for _ in range(1_000)]
    elapsed = perf_counter() - started
    assert len(profiles) == 1_000
    assert elapsed < 5
