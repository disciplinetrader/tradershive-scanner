"""Deterministic AVWAP intelligence tests."""

from datetime import UTC

import numpy as np
import pandas as pd

from app.engine.avwap import AVWAPEngine
from app.models.avwap import AVWAPAnchor, AVWAPAnchorType, AVWAPState


def _frame(direction: float = 1.0, rows: int = 320) -> pd.DataFrame:
    index = pd.bdate_range("2024-01-01", periods=rows, tz="UTC")
    close = np.linspace(100, 160 if direction > 0 else 60, rows)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": np.full(rows, 1_000_000.0),
        },
        index=index,
    )


def test_above_avwap_produces_support() -> None:
    """A persistent advance should sit above and be supported by most anchors."""
    profile = AVWAPEngine().analyze("UP.NS", _frame())
    assert profile.alignment_score >= 80
    assert profile.state in {AVWAPState.SUPPORT, AVWAPState.STRONG_SUPPORT}
    assert profile.support_score > profile.resistance_score


def test_below_avwap_produces_resistance() -> None:
    """A persistent decline should remain below institutional cost bases."""
    profile = AVWAPEngine().analyze("DOWN.NS", _frame(-1))
    assert profile.alignment_score <= 40
    assert profile.resistance_score > profile.support_score
    assert profile.state in {AVWAPState.RESISTANCE, AVWAPState.STRONG_RESISTANCE}


def test_reclaim_and_loss_are_detected() -> None:
    """Latest-session crossings identify reclaim and loss events."""
    frame = _frame()
    anchor = AVWAPAnchor(
        anchor_type=AVWAPAnchorType.USER_DEFINED,
        position=300,
        timestamp=frame.index[300].to_pydatetime().astimezone(UTC),
        label="Event",
    )
    frame.loc[frame.index[-2], "Close"] = 100
    frame.loc[frame.index[-1], "Close"] = 180
    reclaim = AVWAPEngine(resolvers=()).analyze("X", frame, (anchor,))
    assert reclaim.facts.anchors[0].reclaim_detected
    frame.loc[frame.index[-2], "Close"] = 180
    frame.loc[frame.index[-1], "Close"] = 80
    lost = AVWAPEngine(resolvers=()).analyze("X", frame, (anchor,))
    assert lost.facts.anchors[0].loss_detected


def test_multiple_anchors_and_missing_history_warning() -> None:
    """Built-ins coexist and short history transparently lowers assurance."""
    profile = AVWAPEngine().analyze("SHORT", _frame(rows=80))
    assert len(profile.facts.anchors) >= 5
    assert profile.anchor_summary
    assert profile.warnings


def test_custom_resolver_extends_engine_without_logic_changes() -> None:
    """External anchor discovery is accepted through the resolver protocol."""
    frame = _frame()

    class Resolver:
        def resolve(self, data: pd.DataFrame) -> tuple[AVWAPAnchor, ...]:
            return (
                AVWAPAnchor(
                    anchor_type=AVWAPAnchorType.USER_DEFINED,
                    position=100,
                    timestamp=data.index[100].to_pydatetime(),
                    label="Portfolio event",
                ),
            )

    profile = AVWAPEngine((Resolver(),)).analyze("CUSTOM", frame)
    assert set(profile.anchor_summary) == {"Portfolio event"}


def test_missing_columns_rejected() -> None:
    """Incomplete market data cannot produce a fabricated AVWAP."""
    try:
        AVWAPEngine().analyze("BAD", pd.DataFrame({"Close": [1.0]}))
    except ValueError as exc:
        assert "missing columns" in str(exc)
    else:
        raise AssertionError("invalid data accepted")
