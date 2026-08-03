"""Look-ahead-safe replay, forward outcome, and validation aggregation services."""

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from typing import ClassVar

import numpy as np
import pandas as pd

from app.core.v11_config import ScannerProfileConfig
from app.models.stock_result import StockResult
from app.scanner.scanner import Scanner
from app.validation.models import (
    AmbiguityPolicy,
    DataQualitySummary,
    EntryModel,
    FeatureAnalysis,
    HistoricalCandidate,
    HistoricalTrade,
    TradeOutcome,
    ValidationBreakdown,
    ValidationConfig,
    ValidationMetrics,
    ValidationReport,
    WalkForwardPeriod,
    WalkForwardReport,
)


class ForwardOutcomeEvaluator:
    """Evaluate objective entries and exits from post-scan EOD bars."""

    def evaluate(
        self,
        candidate: HistoricalCandidate,
        future: pd.DataFrame,
        config: ValidationConfig,
    ) -> HistoricalTrade:
        """Calculate an outcome without inferring unavailable intraday sequencing."""
        limit = config.maximum_holding_sessions + (
            1 if config.entry_model == EntryModel.NEXT_CLOSE else 0
        )
        bars = future.loc[pd.to_datetime(future.index).date > candidate.scan_date].iloc[:limit]
        if bars.empty:
            return self._untriggered(candidate, TradeOutcome.INVALID)
        entry = self._entry(candidate, bars, config.entry_model)
        if entry is None:
            return self._untriggered(candidate, TradeOutcome.NOT_TRIGGERED)
        entry_position, entry_price = entry
        stop = candidate.stop_price
        if stop is None or stop >= entry_price:
            return self._untriggered(candidate, TradeOutcome.INVALID)
        risk = entry_price - stop
        evaluation_position = (
            entry_position + 1 if config.entry_model == EntryModel.NEXT_CLOSE else entry_position
        )
        active = bars.iloc[evaluation_position:]
        if active.empty:
            return HistoricalTrade(
                candidate=candidate,
                entry_date=pd.Timestamp(bars.index[entry_position]).date(),
                entry_price=entry_price,
                stop_price=stop,
                initial_risk=risk,
                outcome=TradeOutcome.INCOMPLETE,
            )
        high = active["High"].to_numpy(float)
        low = active["Low"].to_numpy(float)
        close = active["Close"].to_numpy(float)
        targets = {multiple: entry_price + risk * multiple for multiple in range(2, 6)}
        target_hits = {multiple: False for multiple in targets}
        stop_hit = False
        ambiguity = False
        exit_offset = len(active) - 1
        exit_price = float(close[-1])
        outcome = TradeOutcome.FLAT
        for offset, (bar_high, bar_low) in enumerate(zip(high, low, strict=True)):
            stop_touched = bar_low <= stop
            reached = [multiple for multiple, target in targets.items() if bar_high >= target]
            selected_touched = config.target_r in reached
            if stop_touched and reached:
                ambiguity = True
                exit_offset = offset
                if config.ambiguity_policy == AmbiguityPolicy.TARGET_FIRST and selected_touched:
                    exit_price, outcome = targets[config.target_r], TradeOutcome.WIN
                    for multiple in reached:
                        if multiple <= config.target_r:
                            target_hits[multiple] = True
                elif config.ambiguity_policy == AmbiguityPolicy.TARGET_FIRST:
                    exit_price, outcome, stop_hit = stop, TradeOutcome.LOSS, True
                    for multiple in reached:
                        target_hits[multiple] = True
                elif config.ambiguity_policy == AmbiguityPolicy.STOP_FIRST:
                    exit_price, outcome, stop_hit = stop, TradeOutcome.LOSS, True
                else:
                    exit_price, outcome = float(close[offset]), TradeOutcome.INVALID
                break
            if stop_touched:
                exit_offset, exit_price, outcome, stop_hit = (
                    offset,
                    stop,
                    TradeOutcome.LOSS,
                    True,
                )
                break
            for multiple, target in targets.items():
                if multiple <= config.target_r and bar_high >= target:
                    target_hits[multiple] = True
            if selected_touched:
                exit_offset, exit_price, outcome = (
                    offset,
                    targets[config.target_r],
                    TradeOutcome.WIN,
                )
                break
        realized_r = (exit_price - entry_price) / risk
        if outcome == TradeOutcome.FLAT:
            outcome = (
                TradeOutcome.WIN
                if realized_r > 0
                else TradeOutcome.LOSS if realized_r < 0 else TradeOutcome.FLAT
            )
        observed_high = high[: exit_offset + 1]
        observed_low = low[: exit_offset + 1]
        mfe = max(0.0, float(np.max(observed_high)) - entry_price)
        mae = max(0.0, entry_price - float(np.min(observed_low)))
        return HistoricalTrade(
            candidate=candidate,
            entry_date=pd.Timestamp(bars.index[entry_position]).date(),
            entry_price=round(entry_price, 4),
            stop_price=stop,
            initial_risk=round(risk, 4),
            maximum_favorable_excursion=round(mfe, 4),
            maximum_adverse_excursion=round(mae, 4),
            mfe_r=round(mfe / risk, 4),
            mae_r=round(mae / risk, 4),
            highest_r_reached=round(
                max(0.0, (float(np.max(observed_high)) - entry_price) / risk), 4
            ),
            target_2r_hit=target_hits[2],
            target_3r_hit=target_hits[3],
            target_4r_hit=target_hits[4],
            target_5r_hit=target_hits[5],
            stop_hit=stop_hit,
            exit_date=pd.Timestamp(active.index[exit_offset]).date(),
            exit_price=round(exit_price, 4),
            realized_r=round(realized_r, 4),
            holding_sessions=exit_offset + 1,
            outcome=outcome,
            ambiguity_flag=ambiguity,
        )

    @staticmethod
    def _entry(
        candidate: HistoricalCandidate, bars: pd.DataFrame, mode: EntryModel
    ) -> tuple[int, float] | None:
        """Resolve an entry only when its objective historical condition occurred."""
        if mode == EntryModel.NEXT_OPEN:
            return 0, float(bars["Open"].iloc[0])
        if mode == EntryModel.NEXT_CLOSE:
            return 0, float(bars["Close"].iloc[0])
        trigger = (
            candidate.pivot_price
            if mode == EntryModel.PIVOT_TRIGGER
            else candidate.risk_entry_price
        )
        if trigger is None:
            return None
        touched = np.flatnonzero(bars["High"].to_numpy(float) >= trigger)
        if not touched.size:
            return None
        position = int(touched[0])
        return position, max(trigger, float(bars["Open"].iloc[position]))

    @staticmethod
    def _untriggered(candidate: HistoricalCandidate, outcome: TradeOutcome) -> HistoricalTrade:
        return HistoricalTrade(candidate=candidate, outcome=outcome)


class HistoricalReplayService:
    """Replay production scanner instances against date-truncated histories."""

    def __init__(self, scanner_factory: Callable[[Mapping[str, pd.DataFrame]], Scanner]) -> None:
        """Accept a factory wired to the same engines/configuration as production."""
        self._scanner_factory = scanner_factory

    def replay(
        self,
        histories: Mapping[str, pd.DataFrame],
        scan_dates: Sequence[date],
        config: ValidationConfig,
        universe_by_date: Mapping[date, Sequence[str]] | None = None,
        sectors: Mapping[str, str] | None = None,
        industries_by_date: Mapping[date, Mapping[str, str]] | None = None,
        scanner_profile: ScannerProfileConfig | None = None,
    ) -> tuple[tuple[HistoricalCandidate, ...], tuple[str, ...]]:
        """Run each unique date using bars at or before that date only."""
        if len(set(scan_dates)) != len(scan_dates):
            raise ValueError("Duplicate historical scan dates are not permitted")
        candidates: list[HistoricalCandidate] = []
        warnings: list[str] = []
        if universe_by_date is None:
            warnings.append("Point-in-time constituents unavailable; survivorship-bias risk exists")
            warnings.append(
                "Delisted-stock omissions cannot be measured without archived universes"
            )
        if sectors is None:
            warnings.append(
                "Historical sector mappings unavailable; current classifications may differ"
            )
        for scan_date in sorted(scan_dates):
            symbols = (
                tuple(universe_by_date.get(scan_date, ())) if universe_by_date else tuple(histories)
            )
            missing = sorted(set(symbols).difference(histories))
            if missing:
                warnings.append(f"{scan_date}: missing symbols: {', '.join(missing)}")
            sliced = {
                symbol: frame.loc[pd.to_datetime(frame.index).date <= scan_date].copy()
                for symbol, frame in histories.items()
                if symbol in symbols
            }
            insufficient = [
                symbol
                for symbol, frame in sliced.items()
                if len(frame) < config.minimum_warmup_sessions
            ]
            if insufficient:
                warnings.append(
                    f"{scan_date}: insufficient warm-up for {', '.join(sorted(insufficient))}"
                )
            anomalous = [
                symbol
                for symbol, frame in sliced.items()
                if frame["Close"].pct_change().abs().gt(0.50).any()
            ]
            if anomalous:
                warnings.append(
                    f"{scan_date}: possible corporate-action anomalies: "
                    f"{', '.join(sorted(anomalous))}"
                )
            eligible = {
                symbol: frame for symbol, frame in sliced.items() if symbol not in insufficient
            }
            if not eligible:
                continue
            industry_mapping = self._mapping_as_of(scan_date, industries_by_date)
            if industries_by_date is not None and industry_mapping is None:
                warnings.append(f"{scan_date}: point-in-time industry mapping unavailable")
            scanner = self._scanner_factory(eligible)
            if industries_by_date is None and scanner_profile is None:
                results = scanner.scan(eligible, sectors)
            else:
                results = scanner.scan(
                    eligible,
                    sectors,
                    industry_mapping,
                    scanner_profile or ScannerProfileConfig(),
                )
            candidates.extend(self._candidates(scan_date, results, config))
        return tuple(candidates), tuple(dict.fromkeys(warnings))

    @staticmethod
    def _mapping_as_of(
        scan_date: date,
        mappings: Mapping[date, Mapping[str, str]] | None,
    ) -> Mapping[str, str] | None:
        """Return only the latest industry mapping known by the scan date."""
        if not mappings:
            return None
        eligible_dates = [mapping_date for mapping_date in mappings if mapping_date <= scan_date]
        return mappings[max(eligible_dates)] if eligible_dates else None

    @staticmethod
    def _candidates(
        scan_date: date, results: Sequence[StockResult], config: ValidationConfig
    ) -> list[HistoricalCandidate]:
        output = []
        for result in results:
            decision = result.decision_profile
            if decision is None or decision.action.value not in config.include_actions:
                continue
            facts = result.facts
            output.append(
                HistoricalCandidate(
                    scan_date=scan_date,
                    symbol=result.symbol,
                    rank=result.rank,
                    decision_score=decision.decision_score,
                    grade=decision.grade.value,
                    action=decision.action.value,
                    setup_type=facts.setup_type.value,
                    market_regime=facts.market_state.value,
                    sector=facts.sector_name,
                    rs_percentile=facts.relative_strength_percentile,
                    volume_state=facts.volume_profile.volume_state.value,
                    cpr_state=facts.cpr_profile.cpr_state.value,
                    avwap_state=facts.avwap_profile.state.value,
                    risk_grade=facts.risk_grade.value,
                    pivot_price=facts.pivot_price,
                    risk_entry_price=facts.entry_price,
                    stop_price=facts.stop_price,
                    advanced_setup_type=facts.setup_profile.best_setup_type.value,
                    volume_signature=facts.volume_profile.volume_signature.value,
                    pocket_pivot=facts.volume_profile.pocket_pivot,
                    hidden_accumulation_score=facts.volume_profile.hidden_accumulation_score,
                    failed_breakout=facts.setup_profile.facts.failed_breakout,
                    market_pressure_score=facts.market_pressure_score,
                    risk_on_state=facts.market_risk_on_state.value,
                    follow_through_state=(
                        "Follow-Through" if facts.market_follow_through_day else "None"
                    ),
                    sector_rotation=facts.sector_rotation.value,
                    industry_group=facts.industry_group,
                    industry_group_rotation=facts.industry_group_rotation.value,
                    scanner_profile=decision.scanner_profile,
                    ipo_age_sessions=facts.setup_profile.facts.ipo_age_sessions,
                    stage_2_first_base=facts.setup_profile.facts.stage_2_first_base,
                    breakout_retest=facts.setup_profile.facts.breakout_retest,
                )
            )
        return output


class ValidationReportBuilder:
    """Build aggregate, dimensional, Top-N, and walk-forward statistics."""

    DIMENSIONS: ClassVar[dict[str, Callable[[HistoricalTrade], str]]] = {
        "score_buckets": lambda trade: self_score_bucket(trade.candidate.decision_score),
        "grades": lambda trade: trade.candidate.grade,
        "actions": lambda trade: trade.candidate.action,
        "setup_types": lambda trade: trade.candidate.setup_type,
        "market_regimes": lambda trade: trade.candidate.market_regime,
        "sectors": lambda trade: trade.candidate.sector,
        "rs_buckets": lambda trade: rs_bucket(trade.candidate.rs_percentile),
        "volume_states": lambda trade: trade.candidate.volume_state,
        "cpr_states": lambda trade: trade.candidate.cpr_state,
        "avwap_states": lambda trade: trade.candidate.avwap_state,
        "risk_grades": lambda trade: trade.candidate.risk_grade,
        "calendar_years": lambda trade: str(trade.candidate.scan_date.year),
        "advanced_setups": lambda trade: trade.candidate.advanced_setup_type,
        "volume_signatures": lambda trade: trade.candidate.volume_signature,
        "pocket_pivot": lambda trade: str(trade.candidate.pocket_pivot),
        "hidden_accumulation": lambda trade: score_band(trade.candidate.hidden_accumulation_score),
        "failed_breakout": lambda trade: str(trade.candidate.failed_breakout),
        "market_pressure": lambda trade: score_band(trade.candidate.market_pressure_score),
        "risk_on_state": lambda trade: trade.candidate.risk_on_state,
        "follow_through": lambda trade: trade.candidate.follow_through_state,
        "sector_rotation": lambda trade: trade.candidate.sector_rotation,
        "industry_groups": lambda trade: trade.candidate.industry_group_rotation,
        "scanner_profiles": lambda trade: trade.candidate.scanner_profile,
        "ipo_age": lambda trade: ipo_age_bucket(trade.candidate.ipo_age_sessions),
        "stage_2_first_base": lambda trade: str(trade.candidate.stage_2_first_base),
        "breakout_retest": lambda trade: str(trade.candidate.breakout_retest),
    }

    def build(
        self,
        trades: Sequence[HistoricalTrade],
        config: ValidationConfig,
        warnings: Sequence[str] = (),
        walk_forward: WalkForwardReport | None = None,
    ) -> ValidationReport:
        """Return a complete report from an immutable trade ledger."""
        breakdowns = {
            name: self._breakdown(name, trades, selector)
            for name, selector in self.DIMENSIONS.items()
        }
        top_n = {
            f"Top {cutoff}": self.metrics(
                [trade for trade in trades if trade.candidate.rank <= cutoff]
            )
            for cutoff in config.top_n_values
        }
        top_n["Full eligible universe"] = self.metrics(trades)
        ambiguity_count = sum(trade.ambiguity_flag for trade in trades)
        quality_warnings = list(warnings)
        if ambiguity_count:
            quality_warnings.append(f"{ambiguity_count} same-bar stop/target ambiguities")
        penalty = min(100.0, len(quality_warnings) * 8.0)
        return ValidationReport(
            config=config,
            metrics=self.metrics(trades),
            breakdowns=breakdowns,
            top_n_comparison=top_n,
            trades=tuple(trades),
            walk_forward=walk_forward,
            data_quality=DataQualitySummary(score=100 - penalty, warnings=tuple(quality_warnings)),
            feature_analysis=self._feature_analysis(trades, breakdowns),
        )

    def _feature_analysis(
        self, trades: Sequence[HistoricalTrade], breakdowns: Mapping[str, ValidationBreakdown]
    ) -> dict[str, FeatureAnalysis]:
        total = max(1, len(trades))
        output = {}
        for dimension, breakdown in breakdowns.items():
            for value, metrics in breakdown.groups.items():
                n = metrics.number_of_triggered_trades
                interval = None
                if n >= 30:
                    p = metrics.win_rate / 100
                    margin = 1.96 * (p * (1 - p) / n) ** 0.5 * 100
                    interval = (
                        round(max(0, metrics.win_rate - margin), 2),
                        round(min(100, metrics.win_rate + margin), 2),
                    )
                output[f"{dimension}:{value}"] = FeatureAnalysis(
                    sample_size=metrics.number_of_candidates,
                    trigger_rate=round(
                        metrics.number_of_triggered_trades
                        / max(1, metrics.number_of_candidates)
                        * 100,
                        2,
                    ),
                    prevalence=round(metrics.number_of_candidates / total * 100, 2),
                    metrics=metrics,
                    win_rate_confidence_interval=interval,
                )
        return output

    @staticmethod
    def metrics(trades: Sequence[HistoricalTrade]) -> ValidationMetrics:
        """Calculate robust empty-safe validation metrics."""
        scans = len({trade.candidate.scan_date for trade in trades})
        triggered = [trade for trade in trades if trade.entry_price is not None]
        if not triggered:
            return ValidationMetrics(
                number_of_scans=scans,
                number_of_candidates=len(trades),
                number_of_triggered_trades=0,
            )
        returns = np.array([trade.realized_r for trade in triggered], dtype=float)
        winners = returns[returns > 0]
        losers = returns[returns < 0]
        equity = np.cumsum(returns)
        drawdown = np.maximum.accumulate(np.insert(equity, 0, 0))[:-1] - equity
        losing_streak = longest_losing_streak(returns)
        denominator = len(triggered)
        gross_loss = float(-losers.sum())
        return ValidationMetrics(
            number_of_scans=scans,
            number_of_candidates=len(trades),
            number_of_triggered_trades=denominator,
            win_rate=round(len(winners) / denominator * 100, 2),
            loss_rate=round(len(losers) / denominator * 100, 2),
            average_realized_r=round(float(returns.mean()), 4),
            median_realized_r=round(float(np.median(returns)), 4),
            expectancy=round(float(returns.mean()), 4),
            profit_factor=round(float(winners.sum()) / gross_loss, 4) if gross_loss else None,
            average_winner_r=round(float(winners.mean()), 4) if winners.size else 0,
            average_loser_r=round(float(losers.mean()), 4) if losers.size else 0,
            maximum_drawdown_r=round(float(max(drawdown, default=0)), 4),
            longest_losing_streak=losing_streak,
            average_holding_period=round(
                float(np.mean([t.holding_sessions for t in triggered])), 2
            ),
            target_2r_hit_rate=hit_rate(triggered, "target_2r_hit"),
            target_3r_hit_rate=hit_rate(triggered, "target_3r_hit"),
            target_4r_hit_rate=hit_rate(triggered, "target_4r_hit"),
            target_5r_hit_rate=hit_rate(triggered, "target_5r_hit"),
            average_mfe=round(float(np.mean([t.mfe_r for t in triggered])), 4),
            average_mae=round(float(np.mean([t.mae_r for t in triggered])), 4),
            exposure=round(
                sum(t.holding_sessions for t in triggered) / (denominator * 40) * 100, 2
            ),
            turnover=round(denominator / max(scans, 1), 2),
        )

    def _breakdown(
        self,
        name: str,
        trades: Sequence[HistoricalTrade],
        selector: Callable[[HistoricalTrade], str],
    ) -> ValidationBreakdown:
        groups: dict[str, list[HistoricalTrade]] = defaultdict(list)
        for trade in trades:
            groups[selector(trade)].append(trade)
        return ValidationBreakdown(
            dimension=name,
            groups={key: self.metrics(value) for key, value in sorted(groups.items())},
        )

    def walk_forward(
        self,
        trades: Sequence[HistoricalTrade],
        windows: Sequence[tuple[date, date, date, date]],
    ) -> WalkForwardReport:
        """Separate fixed-weight in-sample and out-of-sample observations."""
        periods = []
        for in_start, in_end, out_start, out_end in windows:
            if in_end >= out_start:
                raise ValueError("Walk-forward in-sample and out-of-sample periods overlap")
            in_sample = [t for t in trades if in_start <= t.candidate.scan_date <= in_end]
            out_sample = [t for t in trades if out_start <= t.candidate.scan_date <= out_end]
            periods.append(
                WalkForwardPeriod(
                    in_sample_start=in_start,
                    in_sample_end=in_end,
                    out_of_sample_start=out_start,
                    out_of_sample_end=out_end,
                    in_sample_metrics=self.metrics(in_sample),
                    out_of_sample_metrics=self.metrics(out_sample),
                )
            )
        return WalkForwardReport(
            periods=tuple(periods), warnings=("V1 uses fixed production weights only",)
        )


class HistoricalValidationEngine:
    """Coordinate replay, forward evaluation, and reporting without scoring duplication."""

    def __init__(
        self,
        replay: HistoricalReplayService,
        evaluator: ForwardOutcomeEvaluator | None = None,
        builder: ValidationReportBuilder | None = None,
    ) -> None:
        self._replay = replay
        self._evaluator = evaluator or ForwardOutcomeEvaluator()
        self._builder = builder or ValidationReportBuilder()

    def validate(
        self,
        histories: Mapping[str, pd.DataFrame],
        scan_dates: Sequence[date],
        config: ValidationConfig,
        universe_by_date: Mapping[date, Sequence[str]] | None = None,
        sectors: Mapping[str, str] | None = None,
        industries_by_date: Mapping[date, Mapping[str, str]] | None = None,
        scanner_profile: ScannerProfileConfig | None = None,
    ) -> ValidationReport:
        """Replay scans and evaluate every candidate against its complete symbol history."""
        candidates, warnings = self._replay.replay(
            histories,
            scan_dates,
            config,
            universe_by_date,
            sectors,
            industries_by_date,
            scanner_profile,
        )
        trades = [
            self._evaluator.evaluate(candidate, histories[candidate.symbol], config)
            for candidate in candidates
            if candidate.symbol in histories
        ]
        return self._builder.build(trades, config, warnings)


def self_score_bucket(score: float) -> str:
    """Return the requested stable decision-score bucket label."""
    if score >= 95:
        return "95-100"
    if score >= 90:
        return "90-94.99"
    if score >= 85:
        return "85-89.99"
    if score >= 80:
        return "80-84.99"
    if score >= 70:
        return "70-79.99"
    return "Below 70"


def rs_bucket(percentile: float) -> str:
    """Group Relative Strength percentiles into interpretable bands."""
    if percentile >= 90:
        return "90-100"
    if percentile >= 70:
        return "70-89.99"
    if percentile >= 50:
        return "50-69.99"
    return "Below 50"


def score_band(score: float) -> str:
    """Group normalized feature values."""
    return "High" if score >= 70 else "Medium" if score >= 40 else "Low"


def ipo_age_bucket(age: int) -> str:
    """Group IPO ages for evidence reports."""
    if age <= 60:
        return "0-60"
    if age <= 120:
        return "61-120"
    if age <= 252:
        return "121-252"
    return "253+"


def hit_rate(trades: Sequence[HistoricalTrade], field: str) -> float:
    """Return a percentage hit rate for a boolean ledger field."""
    return round(sum(bool(getattr(trade, field)) for trade in trades) / len(trades) * 100, 2)


def longest_losing_streak(returns: np.ndarray) -> int:
    """Return the longest consecutive run of negative realized R."""
    longest = current = 0
    for value in returns:
        current = current + 1 if value < 0 else 0
        longest = max(longest, current)
    return longest
