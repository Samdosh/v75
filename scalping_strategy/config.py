"""
Scalping Bot Configuration
All scalping-specific constants and thresholds
"""

# Dedicated symbol universe for scalping — V75 (R_75) ONLY.
# Every other symbol is explicitly blocked and must never be traded.
BLOCKED_SYMBOLS = {
    "R_25", "R_50", "R_100",
    "1HZ25V", "1HZ50V", "1HZ75V", "1HZ90V",
    "1HZ100V", "1HZ30V",
    "stpRNG5", "stpRNG4",
}
SYMBOLS = ["R_75"]

# Empty rollout list means: trade full scalping symbol universe.
SCALPING_ROLLOUT_SYMBOLS = []

# Dedicated asset config for scalping (duplicated intentionally for isolation).
ASSET_CONFIG = {
    "R_75": {
        "multiplier": 50,
        "description": "Volatility 75 Index",
        "tick_size": 0.01,
        "movement_threshold_pct": 0.8,
        "entry_distance_pct": 0.8,
    },
}

# ==================== SCALPING STRATEGY PARAMETERS ====================
# Scalping bot uses relaxed thresholds for more frequent trading

SCALPING_TIMEFRAMES = ["1h", "5m", "1m"]
SCALPING_ADX_THRESHOLD = 25
SCALPING_ADX_MAX_THRESHOLD = 34
SCALPING_STPRNG4_MIN_ADX = 35
SCALPING_RSI_UP_MIN = 58
SCALPING_RSI_UP_MAX = 72
SCALPING_RSI_DOWN_MIN = 28
SCALPING_RSI_DOWN_MAX = 42
SCALPING_MAX_PRICE_MOVEMENT_PCT = 1.2
SCALPING_MOMENTUM_THRESHOLD = 1.0  # ATR multiplier
SCALPING_MIN_RR_RATIO = 1.4
# Floating-point guard so values effectively equal to min R:R are not rejected.
SCALPING_RR_TOLERANCE = 0.01
# Final report recommendation (Feb 25-27, 2026):
# widen both SL/TP proportionally to preserve 1.5 R:R while reducing premature stop-outs.
SCALPING_SL_ATR_MULTIPLIER = 2.0
SCALPING_TP_ATR_MULTIPLIER = 3.0
SCALPING_BODY_RATIO_MIN = 0.65
SCALPING_ADX_SLOPE_MIN = -2.0
SCALPING_ZONE_TOLERANCE_PCT = 0.0015
SCALPING_1M_DIRECTIONAL_SEQUENCE_CANDLES = 3
SCALPING_MAX_ENTRY_DRIFT_ATR = 0.35
# 5m EMA fallback minimum slope (percent change per closed candle) used when
# there is no recent fresh crossover.
SCALPING_5M_EMA_SLOPE_MIN_PCT = 0.005

# Asset-specific movement thresholds (conservative × 1.7)
SCALPING_ASSET_MOVEMENT_MULTIPLIER = 1.7

# Directional safety gate: suspend DOWN signals everywhere except allowlist.
SCALPING_DOWN_DIRECTION_FILTER_ENABLED = False
SCALPING_DOWN_ALLOWED_SYMBOLS = {"R_75"}

# Per-symbol ADX minimum overrides (directional). V75-only universe; no overrides needed.
SCALPING_SYMBOL_ADX_OVERRIDES = {}

# ==================== SCALPING RISK MANAGEMENT ====================
# Portfolio-wide concurrent cap across all symbols.
SCALPING_MAX_CONCURRENT_TRADES = 1
# Per-symbol concurrent cap (single asset may only have one open trade).
SCALPING_MAX_CONCURRENT_PER_SYMBOL = 1
SCALPING_COOLDOWN_SECONDS = 30
SCALPING_MAX_TRADES_PER_DAY = 5
# Hard safety cap to prevent accidental overtrading if config drifts.
SCALPING_HARD_MAX_TRADES_PER_DAY = 5
SCALPING_MAX_CONSECUTIVE_LOSSES = 3
SCALPING_GLOBAL_LOSS_COOLDOWN_SECONDS = 3 * 60 * 60
SCALPING_DAILY_LOSS_MULTIPLIER = 2.0

# Symbol-level cooldown after repeated losses on the same symbol.
SCALPING_SYMBOL_MAX_CONSECUTIVE_LOSSES = 2
SCALPING_SYMBOL_LOSS_COOLDOWN_SECONDS = 45 * 60
SCALPING_SINGLE_LOSS_COOLDOWN_SECONDS = 10 * 60

# Fast-loss suppression: if losses close too quickly, pause that symbol.
SCALPING_SHORT_LOSS_DURATION_SECONDS = 60
SCALPING_SHORT_LOSS_LOOKBACK_SECONDS = 2 * 60 * 60
SCALPING_SHORT_LOSS_COUNT_THRESHOLD = 2
SCALPING_SHORT_LOSS_COOLDOWN_SECONDS = 30 * 60

# Rolling regime guard (3-day win-rate monitor) to halt trading
# when recent market conditions degrade.
SCALPING_PERFORMANCE_WINDOW_DAYS = 3
SCALPING_PERFORMANCE_MIN_TRADES = 10
SCALPING_PERFORMANCE_MIN_WIN_RATE_PCT = 35.0
SCALPING_PERFORMANCE_COOLDOWN_SECONDS = 3 * 60 * 60

# ==================== MARKET REGIME DETECTION ====================
SCALPING_ENABLE_REGIME_ADAPTATION = True
SCALPING_REGIME_ADX_TREND_THRESHOLD = 25.0
SCALPING_REGIME_ATR_VOLATILE_PERCENTILE = 80.0
SCALPING_REGIME_ATR_LOOKBACK = 100

# ==================== DEAD MARKET FILTER ====================
SCALPING_ENABLE_DEAD_MARKET_FILTER = True
SCALPING_DEAD_MARKET_ATR_PERCENTILE = 20.0
SCALPING_DEAD_MARKET_ATR_LOOKBACK = 100

# ==================== ZONE-BASED SL ====================
SCALPING_ENABLE_ZONE_BASED_SL = True
SCALPING_ZONE_PROXIMITY_PCT = 0.0015

# ==================== HYBRID SL/TP ====================
SCALPING_ENABLE_HYBRID_SL_TP = True
SCALPING_HYBRID_SL_MIN_ATR = 0.5
SCALPING_HYBRID_SL_MAX_ATR = 2.5
SCALPING_HYBRID_TP_MAX_ATR = 4.0

# ==================== RUNAWAY TRADE PROTECTION ====================
SCALPING_RUNAWAY_WINDOW_MINUTES = 10
SCALPING_RUNAWAY_TRADE_COUNT = 10

# ==================== STAGNATION EXIT ====================
# Final report recommendation (Feb 25-27, 2026):
# cut stagnation losers earlier without touching winners (which are positive early).
SCALPING_STAGNATION_EXIT_TIME = 76  # seconds
SCALPING_STAGNATION_LOSS_PCT = 4  # percentage of stake
SCALPING_STAGNATION_RR_GRACE_THRESHOLD = 2.5
SCALPING_STAGNATION_EXTRA_TIME = 0  # disabled by default for strict 75s/3.0% behavior

SCALPING_SYMBOL_STAGNATION_OVERRIDES = {
    "R_75": 120,
}

# ==================== TRAILING PROFIT ====================
# Activate trailing as soon as profit reaches 6%.
SCALPING_TRAIL_ACTIVATION_PCT = 6.0

# Dynamic trailing distance tiers: (min_profit_pct, trail_distance_pct)
# Tiers are checked from highest to lowest; first match wins.
SCALPING_TRAIL_TIERS = [
    (25.0, 7.0),   # 25%+ profit -> 7% trail distance
    (15.0, 5.0),   # 15-25% profit -> 5% trail distance
    (10.0, 4.0),    # 8-15% profit -> 4% trail distance
]

# Hard floor after trailing activation: do not allow profitable activated trades
# to be held into negative P&L.
SCALPING_TRAIL_BREAKEVEN_FLOOR_PCT = 0.0

# Optional anti-whipsaw guard (global defaults).
# If a trade dips below trail floor, require this many consecutive checks before exit.
SCALPING_TRAIL_BREACH_CONFIRMATIONS = 2
# Minimum time after trailing activation before floor breaches can force an exit.
SCALPING_TRAIL_MIN_ACTIVE_SECONDS = 10

# Per-symbol trailing overrides. V75-only universe; none needed.
SCALPING_SYMBOL_TRAIL_OVERRIDES = {}
