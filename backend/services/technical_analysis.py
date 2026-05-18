"""
BTF – Analyse Technique (Module C)
EMA, RSI, MACD, Bandes de Bollinger, ATR
"""

import numpy as np
from typing import Optional


class TechnicalAnalysis:
    """
    Moteur d'analyse technique complet.
    Calcule tous les indicateurs et génère un score composite.
    """

    @staticmethod
    def ema(data: np.ndarray, period: int) -> np.ndarray:
        alpha = 2 / (period + 1)
        ema_values = np.zeros_like(data)
        ema_values[0] = data[0]
        for i in range(1, len(data)):
            ema_values[i] = alpha * data[i] + (1 - alpha) * ema_values[i - 1]
        return ema_values

    @staticmethod
    def rsi(closes: np.ndarray, period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0
        deltas = np.diff(closes)
        gains  = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 2)

    @staticmethod
    def macd(closes: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
        if len(closes) < slow + signal:
            return {"macd": 0, "signal": 0, "histogram": 0, "bullish_cross": False}
        ema_fast  = TechnicalAnalysis.ema(closes, fast)
        ema_slow  = TechnicalAnalysis.ema(closes, slow)
        macd_line = ema_fast - ema_slow
        signal_line = TechnicalAnalysis.ema(macd_line, signal)
        histogram = macd_line - signal_line
        bullish_cross = (macd_line[-1] > signal_line[-1]) and (macd_line[-2] <= signal_line[-2])
        bearish_cross = (macd_line[-1] < signal_line[-1]) and (macd_line[-2] >= signal_line[-2])
        return {
            "macd":        round(float(macd_line[-1]), 6),
            "signal":      round(float(signal_line[-1]), 6),
            "histogram":   round(float(histogram[-1]), 6),
            "bullish_cross": bullish_cross,
            "bearish_cross": bearish_cross,
        }

    @staticmethod
    def bollinger_bands(closes: np.ndarray, period: int = 20, std_dev: float = 2.0) -> dict:
        if len(closes) < period:
            c = float(closes[-1])
            return {"upper": c, "middle": c, "lower": c, "width": 0, "position": 0.5}
        sma    = np.mean(closes[-period:])
        std    = np.std(closes[-period:])
        upper  = sma + std_dev * std
        lower  = sma - std_dev * std
        current = float(closes[-1])
        width  = (upper - lower) / sma if sma != 0 else 0
        position = (current - lower) / (upper - lower) if (upper - lower) != 0 else 0.5
        return {
            "upper":    round(upper, 6),
            "middle":   round(sma, 6),
            "lower":    round(lower, 6),
            "width":    round(width, 4),
            "position": round(position, 4),   # 0=lower, 0.5=middle, 1=upper
        }

    @staticmethod
    def atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
        if len(closes) < 2:
            return 0.0
        trs = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            trs.append(tr)
        return round(float(np.mean(trs[-period:])), 6)

    @staticmethod
    def volume_trend(volumes: np.ndarray, period: int = 20) -> str:
        if len(volumes) < period:
            return "neutral"
        avg = np.mean(volumes[-period:-1])
        current = volumes[-1]
        if current > avg * 1.5:
            return "high"
        elif current < avg * 0.5:
            return "low"
        return "normal"

    @classmethod
    def analyze(
        cls,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        volumes: np.ndarray,
    ) -> dict:
        """
        Analyse complète – retourne tous les indicateurs + score composite [-1, +1].
        """
        rsi_val   = cls.rsi(closes)
        macd_data = cls.macd(closes)
        bb        = cls.bollinger_bands(closes)
        ema20     = cls.ema(closes, 20)
        ema50     = cls.ema(closes, 50)
        ema200    = cls.ema(closes, 200)
        atr_val   = cls.atr(highs, lows, closes)
        vol_trend = cls.volume_trend(volumes)

        current = float(closes[-1])
        ema20_last  = float(ema20[-1])
        ema50_last  = float(ema50[-1])
        ema200_last = float(ema200[-1])

        ema_bullish  = ema20_last > ema50_last
        price_above_ema20 = current > ema20_last
        price_above_ema50 = current > ema50_last

        # ── SCORING ────────────────────────────────────────────────────────────
        score = 0.0

        # RSI (±0.3)
        if rsi_val < 30:
            score += 0.3    # Survendu → signal achat
        elif rsi_val > 70:
            score -= 0.3    # Suracheté → signal vente
        elif 40 <= rsi_val <= 60:
            score += 0.0    # Neutre

        # MACD (±0.25)
        if macd_data["bullish_cross"]:
            score += 0.25
        elif macd_data["bearish_cross"]:
            score -= 0.25
        elif macd_data["histogram"] > 0:
            score += 0.1
        elif macd_data["histogram"] < 0:
            score -= 0.1

        # EMA (±0.2)
        if ema_bullish:
            score += 0.15
        else:
            score -= 0.15
        if price_above_ema20:
            score += 0.05
        else:
            score -= 0.05

        # Bollinger Bands (±0.15)
        if bb["position"] < 0.1:
            score += 0.15   # Prix près de la bande basse → rebond potentiel
        elif bb["position"] > 0.9:
            score -= 0.15   # Prix près de la bande haute → correction potentielle

        # Volume (±0.1)
        if vol_trend == "high" and score > 0:
            score += 0.1    # Volume élevé confirme signal haussier
        elif vol_trend == "high" and score < 0:
            score -= 0.1

        score = max(-1.0, min(1.0, score))

        return {
            "score":        round(score, 4),
            "rsi":          rsi_val,
            "macd":         macd_data["macd"],
            "macd_signal":  macd_data["signal"],
            "macd_hist":    macd_data["histogram"],
            "macd_bullish": macd_data["bullish_cross"],
            "ema20":        round(ema20_last, 4),
            "ema50":        round(ema50_last, 4),
            "ema200":       round(ema200_last, 4),
            "ema_bullish":  ema_bullish,
            "bb_upper":     bb["upper"],
            "bb_middle":    bb["middle"],
            "bb_lower":     bb["lower"],
            "bb_position":  bb["position"],
            "atr":          atr_val,
            "volume_trend": vol_trend,
            "current_price": current,
        }
