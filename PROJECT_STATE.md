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
- Dedicated research scoring tests exist.

## Last validated baseline
- Historical Backtest #26 completed successfully; validate, six-month replay, result validation and artifact publication all passed.
- Weighted evidence metrics showed the legacy confluence value could reach 100% despite weak evidence coverage.
- Previous 6-month OOS snapshot:
  - 5m: 47 closed trades, 0 wins, 47 losses, 0% win rate, PF 0.00, return -1.175%.
  - 15m: 18 closed trades, 2 wins, 16 losses, PF 1.22, return +0.091% (too small for conclusions).
  - 1h: 4 closed trades, 1 win, 3 losses, PF 3.05, return +0.168% (far too small).

## Current implementation state
The continuous research scoring batch is committed on `main` and has NOT yet had its own Code Quality + Historical Backtest cycle. Do not treat it as validated or profitable.

## Next step
1. Run Code Quality once for the current continuous research-scoring batch.
2. If green, run exactly one Historical Backtest.
3. Compare continuous scores vs legacy scores and outcomes by timeframe/regime; inspect score distributions and sample sizes.
4. Do not modify LIVE based on a single backtest.

## Do not do
- Do not launch multiple identical Historical Backtests.
- Do not call a small sample profitable based on PF alone.
- Do not optimize against OOS.
- Do not move research scoring into LIVE without a dedicated validation cycle.

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
