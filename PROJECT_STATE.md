# Trading Bot — Project State

## Purpose
This file is the recovery checkpoint for continuing development in a new ChatGPT conversation. The GitHub repository is the source of truth for code and workflow state; this document records the current project context and decisions.

## Current target
- Target: V1.0 frozen and fully validated by 2026-12-15.
- Current phase: Research / Signal Analytics / scoring refinement.
- LIVE trading logic must remain isolated from research experiments unless explicitly approved and validated.

## Development cadence
Use batch development rather than checking every micro-change:
BUILD -> BUILD -> BUILD -> CODE QUALITY -> HISTORICAL BACKTEST -> ANALYSIS.
For sensitive LIVE/risk/execution changes, validate immediately.

## Architecture / principles
- Candle convention: candle 0 = forming candle; candle 1 = latest fully closed candle. Research/backtest must not trade on candle 0.
- Historical replay is the research path.
- LIVE signal path is kept separate from research scoring experiments.
- Code Quality is the safety gate before a new historical backtest.
- Historical backtest artifacts are used for quantitative analysis.

## Completed / current components
- Historical Backtest GitHub Actions workflow is operational.
- Code Quality workflow is operational.
- Signal Analytics includes weighted evidence metrics.
- Research scoring has been added for continuous Trend / Momentum / Setup scores.
- Current research scoring intent:
  - Trend: EMA50 distance + Ichimoku context.
  - Momentum: RSI + MACD histogram.
  - Setup: Bollinger + Fibonacci + Price Action.
  - Scores normalized to 0-100.
- Research replay adapter integrates the research scoring path while retaining legacy production scoring for comparison.
- Dedicated tests were added for research scoring range/direction behavior.

## Recent validation
- Historical Backtest #26 completed successfully.
- Code Quality for the weighted-evidence change completed successfully.
- Historical artifact was generated successfully.
- Previous OOS snapshot from the 6-month replay showed:
  - 5m: 47 closed trades, 0 wins, 47 losses, 0% win rate, PF 0.00, return -1.175%.
  - 15m: 18 closed trades, 2 wins, 16 losses, PF 1.22, return +0.091% (sample too small for conclusions).
  - 1h: 4 closed trades, 1 win, 3 losses, PF 3.05, return +0.168% (sample far too small).
- The old confluence metric could show 100% even when evidence coverage was weak; weighted evidence metrics were added to prevent that interpretation error.

## Important current finding
Trend, Momentum and Setup were previously derived too coarsely and often collapsed to identical 0/100-style values. The current batch introduces continuous research scores. The next validation must determine whether these scores are genuinely informative and whether the implementation is independent enough to avoid duplicated information.

## Next step
1. Run Code Quality once for the current research-scoring batch.
2. If green, run exactly one Historical Backtest.
3. Compare continuous research scores against legacy scoring and outcomes by timeframe/regime.
4. Do not modify LIVE behavior based on a single backtest.

## Do not do
- Do not launch multiple identical Historical Backtests.
- Do not call a small sample profitable based on PF alone.
- Do not optimize against the OOS set.
- Do not move research scoring into LIVE without a dedicated validation cycle.

## Recovery rule for a new chat
Start by reading this file, then inspect the latest commits/workflows/artifacts. Continue from the Next step section rather than reconstructing the entire conversation.

## Roadmap highlights
1. Signal Analytics and scoring integrity
2. Market Regime Engine
3. Multi-timeframe context
4. Realistic execution costs/slippage
5. Walk-forward + Monte Carlo validation
6. Shadow/paper trading
7. Only later consider ML and real capital
