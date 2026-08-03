# Scanner v1.1 Advanced Momentum Intelligence

Version 1.1 adds objective advanced setup, volume-event, market-pressure, and industry-group
evidence without replacing the v1.0 scoring architecture. The original adaptive decision score is
calculated first; configurable context gates then determine whether the candidate remains a BUY,
becomes a WATCHLIST item, or must be avoided.

All pattern detection uses completed EOD bars. Earnings-gap consolidation requires explicit
catalyst dates; without them the detector reports missing catalyst data and never labels the event
as earnings-driven. Industry mappings are supplied by callers. Missing mappings retain stock
eligibility with neutral group evidence and reduced confidence.

Threshold families live in `app/core/v11_config.py`: advanced setups, volume events,
follow-through rules, market pressure, industry ranking, decision gates, and scanner profiles.
Profiles change eligibility gates only and do not mutate production weights.

Historical validation snapshots all v1.1 evidence at scan time and reports cohorts for advanced
setups, volume signatures, pocket pivots, accumulation, failures, market pressure, risk posture,
industry rotation, scanner profile, IPO age, Stage 2 first bases, and breakout retests. Feature
reports are evidence only; no automatic optimization occurs.

Known EOD limitations remain: daily candles cannot establish intraday stop/target order, earnings
events require external timestamped data, current industry mappings can create classification bias,
and point-in-time constituent archives are required to control survivorship bias.
