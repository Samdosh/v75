"""
Market Regime Detection & Adaptive SL/TP Module

Provides:
  1. Regime classification (trending / ranging / volatile) via ADX + ATR percentile
  2. Regime-adjusted SL/TP multipliers and min R:R
  3. Zone-based SL (clusters of swing points instead of single levels)
  4. Dead-market filter (skip trading when ATR is below historical percentile)
  5. Hybrid SL/TP calculator (combines ATR-based and structure-based levels)
"""

from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


class MarketRegime(Enum):
    TRENDING = "trending"
    RANGING = "ranging"
    VOLATILE = "volatile"


# ---------------------------------------------------------------------------
# 1. Regime detection
# ---------------------------------------------------------------------------

def detect_market_regime(
    adx_val: float,
    atr_val: float,
    atr_percentile: float,
    adx_trend_threshold: float = 25.0,
    atr_volatile_percentile: float = 80.0,
) -> MarketRegime:
    if atr_percentile >= atr_volatile_percentile:
        return MarketRegime.VOLATILE
    if adx_val >= adx_trend_threshold:
        return MarketRegime.TRENDING
    return MarketRegime.RANGING


def atr_percentile(
    df: pd.DataFrame,
    period: int = 14,
    lookback: int = 100,
) -> float:
    """
    Return where the *latest* ATR sits in the historical distribution
    (0–100).  Higher = more volatile than usual.
    """
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - df["close"].shift()).abs()
    tr3 = (df["low"] - df["close"].shift()).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr_series = true_range.rolling(period).mean().dropna()

    if len(atr_series) < lookback:
        return 50.0

    historical = atr_series.tail(lookback)
    current_atr = atr_series.iloc[-1]
    percentile = (historical < current_atr).mean() * 100.0
    return float(percentile)


# ---------------------------------------------------------------------------
# 2. Regime-adjusted parameters
# ---------------------------------------------------------------------------

def get_regime_params(
    regime: MarketRegime,
    base_min_rr: float = 1.8,
) -> Dict:
    """
    Return SL/TP multipliers and min R:R tuned per regime.

    - TRENDING  → tighter SL, high R:R  (trend has follow-through)
    - RANGING   → tightest SL, highest R:R (mean-reversion risk)
    - VOLATILE  → wider SL, relaxed R:R   (noise requires breathing room)
    """
    _params = {
        MarketRegime.TRENDING: {
            "sl_atr_mult": 1.5,
            "tp_atr_mult": 3.0,
            "min_rr": base_min_rr,
            "max_sl_distance_pct": 0.9,
            "regime_name": "Trending",
        },
        MarketRegime.RANGING: {
            "sl_atr_mult": 1.0,
            "tp_atr_mult": 2.5,
            "min_rr": round(base_min_rr * 1.15, 2),
            "max_sl_distance_pct": 0.5,
            "regime_name": "Ranging",
        },
        MarketRegime.VOLATILE: {
            "sl_atr_mult": 2.5,
            "tp_atr_mult": 4.0,
            "min_rr": round(base_min_rr * 0.85, 2),
            "max_sl_distance_pct": 1.5,
            "regime_name": "Volatile",
        },
    }
    return _params.get(regime, _params[MarketRegime.TRENDING])


# ---------------------------------------------------------------------------
# 3. Zone‑based SL
# ---------------------------------------------------------------------------

def identify_demand_supply_zones(
    swing_points: List[float],
    zone_proximity_pct: float = 0.0015,
) -> List[Dict]:
    """
    Group nearby swing points into supply/demand **zones**.

    Each zone dict:
        'avg_price'   – average of every swing in the cluster
        'low'         – lowest swing in the cluster
        'high'        – highest swing in the cluster
        'touches'     – how many swing points are inside the zone
        'strength'    – 1–10 score based on touches (more touches = stronger)
    """
    if not swing_points:
        return []

    points = sorted(swing_points)
    clusters: List[List[float]] = [[points[0]]]

    for p in points[1:]:
        if clusters[-1][-1] > 0 and p / clusters[-1][-1] - 1.0 <= zone_proximity_pct:
            clusters[-1].append(p)
        else:
            clusters.append([p])

    zones: List[Dict] = []
    for cluster in clusters:
        avg = sum(cluster) / len(cluster)
        zones.append(
            {
                "avg_price": avg,
                "low": min(cluster),
                "high": max(cluster),
                "touches": len(cluster),
                "strength": min(10.0, len(cluster) * 2.0),
            }
        )
    return zones


def find_nearest_zone(
    zones: List[Dict],
    current_price: float,
    direction: str,
) -> Optional[Dict]:
    """
    For a given trade direction return the zone that acts as the nearest
    structural barrier behind the entry.

    - UP   → nearest demand zone *below* price
    - DOWN → nearest supply zone *above* price
    """
    if direction == "UP":
        candidates = [z for z in zones if z["avg_price"] < current_price]
        if candidates:
            return max(candidates, key=lambda z: z["avg_price"])
    else:
        candidates = [z for z in zones if z["avg_price"] > current_price]
        if candidates:
            return min(candidates, key=lambda z: z["avg_price"])
    return None


# ---------------------------------------------------------------------------
# 4. Dead‑market filter
# ---------------------------------------------------------------------------

def is_dead_market(
    df_5m: pd.DataFrame,
    atr_period: int = 14,
    percentile_threshold: float = 20.0,
    lookback: int = 100,
) -> bool:
    """
    Return True when the current 5m ATR is below the ``percentile_threshold``
    percentile of its recent history.  A dead market lacks follow‑through
    and should be skipped.
    """
    pct = atr_percentile(df_5m, atr_period, lookback)
    return pct < percentile_threshold


# ---------------------------------------------------------------------------
# 5. Hybrid SL/TP calculators
# ---------------------------------------------------------------------------

def hybrid_sl_price(
    direction: str,
    current_price: float,
    atr: float,
    structure_sl: Optional[float],
    zones: Optional[List[Dict]] = None,
    sl_atr_mult: float = 2.0,
    min_structure_sl_atr: float = 0.5,
    max_sl_atr: float = 2.5,
) -> float:
    """
    Compute SL that respects both ATR volatility and market structure.

    Priority:
      1. Nearest demand/supply ZONE  (if zones provided)
      2. Single swing‑point SL       (if structure_sl supplied)
      3. ATR‑based fallback          (always)

    If the structural level is **too close** (< min_structure_sl_atr) the
    level is used anyway because it represents a strong barrier.  If it is
    **too far** (> max_sl_atr) the SL is capped at max_sl_atr × ATR.
    """
    best_sl: Optional[float] = None

    # --- zone‑based SL (strongest) ---
    if zones:
        nearest = find_nearest_zone(zones, current_price, direction)
        if nearest:
            if direction == "UP":
                best_sl = nearest["low"]
            else:
                best_sl = nearest["high"]

    # --- fallback to single swing point ---
    if best_sl is None and structure_sl is not None:
        dist_atr = abs(current_price - structure_sl) / atr if atr > 0 else 999
        if dist_atr <= max_sl_atr:
            best_sl = structure_sl
        else:
            # cap at max ATR distance
            if direction == "UP":
                best_sl = current_price - (atr * max_sl_atr)
            else:
                best_sl = current_price + (atr * max_sl_atr)

    # --- pure ATR fallback ---
    if best_sl is None:
        if direction == "UP":
            best_sl = current_price - (atr * sl_atr_mult)
        else:
            best_sl = current_price + (atr * sl_atr_mult)

    # Safety: enforce minimum distance from entry
    min_dist = atr * min_structure_sl_atr
    actual_dist = abs(current_price - best_sl)
    if actual_dist < min_dist and atr > 0:
        # SL is too close — keep it (strong structural level), but clamp minimum
        if direction == "UP":
            best_sl = min(best_sl, current_price - min_dist)
        else:
            best_sl = max(best_sl, current_price + min_dist)

    return best_sl


def hybrid_tp_price(
    direction: str,
    current_price: float,
    atr: float,
    structure_tp: Optional[float],
    tp_atr_mult: float = 3.0,
    max_tp_atr: float = 4.0,
    min_tp_distance_pct: float = 0.2,
    tp_buffer_pct: float = 0.1,
) -> float:
    """
    Compute TP that respects both ATR volatility and structure.

    If a structure TP is within [min_tp_distance_pct, max_tp_atr × ATR]:
        → use it (minus buffer).
    Otherwise:
        → fall back to ATR‑based TP.
    """
    atr_tp_distance = atr * tp_atr_mult

    # ATR‑based fallback
    if direction == "UP":
        fallback_tp = current_price + atr_tp_distance
    else:
        fallback_tp = current_price - atr_tp_distance

    if structure_tp is None:
        return fallback_tp

    tp_dist_pct = abs(structure_tp - current_price) / current_price * 100.0
    tp_dist_atr = abs(structure_tp - current_price) / atr if atr > 0 else 999

    # Too close → can't use structure, fall back to ATR
    if tp_dist_pct < min_tp_distance_pct:
        return fallback_tp

    # Too far → unrealistic R:R, fall back to ATR
    if tp_dist_atr > max_tp_atr:
        return fallback_tp

    # Within acceptable range → use structure with early‑exit buffer
    buffer_offset = (tp_buffer_pct / 100.0) * structure_tp
    if direction == "UP":
        return structure_tp - buffer_offset
    else:
        return structure_tp + buffer_offset
