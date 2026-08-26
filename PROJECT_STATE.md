# Trading Bot — Project State

## Purpose
Recovery checkpoint for continuing development in a new ChatGPT conversation. GitHub is the source of truth for code and workflow state; this document records project context and decisions.

## Current target
- Target: V1.0 frozen and fully validated by 2026-12-15.
- Current phase: Research / Signal Analytics / scoring refinement.
- LIVE trading logic remains isolated from research experiments unless explicitly approved and validated.

## Development cadence
Batch development: BUILD -> BUILD -> BUILD -> CODE QUALITY -> HISTORICAL BACKTEST -> ANALYSIS. Sensitive LIVE/risk/execution changes are validated immediately.

## Architecture / principles
- Candle convention: candle 0 = forming candle; candle 1 = latest fully closed candle. Research/backtest must not trade on candle 0.
- Historical replay is the research path.
- LIVE signal path is separate from research scoring experiments.
- Code Quality is the safety gate before a new historical backtest.
- Historical backtest artifacts are used for quantitative analysis.

## Current components
- Historical Backtest GitHub Actions workflow operational.
- Code Quality workflow operational.
- Signal Analytics includes weighted evidence metrics.
- `research_scoring.py` provides research-only continuous Trend / Momentum / Setup scores, normalized 0-100.
- Research scoring intent:
  - Trend: continuous price-vs-EMA50 distance + Ichimoku direction.
  - Momentum: continuous RSI position + MACD histogram.
  - Setup: Bollinger + Fibonacci + Price Action evidence with neutral evidence preserved.
- `signal_engine_replay_adapter_fast.py` uses research continuous categories for historical classification while retaining legacy production categories for comparison.
- `research_score_analysis.py` measures score separation across train/validation/OOS without selecting a production threshold.
- Dedicated research scoring and score-analysis tests exist.

## Last validated baseline
- Historical Backtest #30 completed successfully on 2026-08-26 after the continuous research-scoring batch.
- Artifact publication succeeded.
- The run still reports only Node.js 20 deprecation warnings; no workflow failure.
- Current 6-month OOS snapshot:
  - 5m: portfolio return -1.3297%, PF 0.36; unsuitable for the current research focus.
  - 15m: portfolio return -0.4544%, PF 0.69; no demonstrated edge.
  - 1h: portfolio return +0.5143%, PF 1.52, expectancy +0.0147%; promising but still too small for a profitability claim.
- Continuous score separation ranks timeframes: 1h > 5m > 15m.
- 1h currently has the strongest score separation (high-score vs low-score win-rate lift about +4.09 percentage points), but monotonicity is NOT consistent across all train/validation/OOS partitions.
- Therefore 1h is the primary research timeframe for the next diagnostic cycle, not a LIVE or production recommendation.

## Current implementation state
The continuous research-scoring batch is validated by Code Quality + Historical Backtest. It is research-only and must not be moved into LIVE based on this result.

## Next step
1. Focus the next diagnostic cycle on 1h.
2. Run a chronological/walk-forward stability analysis of score separation by partition and market regime; do not optimize against OOS.
3. If the 1h relationship remains stable, expand the analysis to multi-timeframe confirmation (15m + 1h) without changing LIVE logic.
4. Only after stable evidence, evaluate realistic costs/slippage and broader robustness.

## Do not do
- Do not launch multiple identical Historical Backtests.
- Do not call a small sample profitable based on PF alone.
- Do not optimize against OOS.
- Do not move research scoring into LIVE without a dedicated validation cycle.
- Do not treat the 1h result as a trading recommendation yet.

## Recovery rule
For a new chat: read this file first, inspect latest commits/workflows/artifacts, then continue from Next step.

## Roadmap
1. Signal Analytics and scoring integrity
2. Market Regime Engine
3. Multi-timeframe context
4. Realistic execution costs/slippage
5. Walk-forward + Monte Carlo validation
6. Shadow/paper trading
7. Only later consider ML and real capital
