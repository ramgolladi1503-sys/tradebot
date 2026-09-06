from __future__ import annotations

def ema(values: list[float], length: int) -> list[float | None]:
    if length <= 0:
        raise ValueError("length must be positive")
    out: list[float | None] = [None] * len(values)
    if len(values) < length:
        return out
    seed = sum(values[:length]) / length
    out[length - 1] = seed
    alpha = 2.0 / (length + 1.0)
    prev = seed
    for i in range(length, len(values)):
        prev = alpha * values[i] + (1.0 - alpha) * prev
        out[i] = prev
    return out

def wma(values: list[float | None], length: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    weights = list(range(1, length + 1))
    denom = float(sum(weights))
    for i in range(length - 1, len(values)):
        window = values[i-length+1:i+1]
        if any(v is None for v in window):
            continue
        out[i] = sum(float(v) * w for v, w in zip(window, weights)) / denom
    return out

def rsi_wilder(values: list[float], length: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) <= length:
        return out
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, length + 1):
        delta = values[i] - values[i-1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains) / length
    avg_loss = sum(losses) / length
    def calc(gain: float, loss: float) -> float:
        if loss == 0:
            return 100.0
        rs = gain / loss
        return 100.0 - 100.0 / (1.0 + rs)
    out[length] = calc(avg_gain, avg_loss)
    for i in range(length + 1, len(values)):
        delta = values[i] - values[i-1]
        gain, loss = max(delta, 0.0), max(-delta, 0.0)
        avg_gain = ((length - 1) * avg_gain + gain) / length
        avg_loss = ((length - 1) * avg_loss + loss) / length
        out[i] = calc(avg_gain, avg_loss)
    return out

def atr_wilder(high: list[float], low: list[float], close: list[float], length: int) -> list[float | None]:
    true_ranges: list[float] = []
    for i in range(len(close)):
        if i == 0:
            true_ranges.append(high[i] - low[i])
        else:
            true_ranges.append(max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1])))
    out: list[float | None] = [None] * len(close)
    if len(true_ranges) < length:
        return out
    prev = sum(true_ranges[:length]) / length
    out[length - 1] = prev
    for i in range(length, len(true_ranges)):
        prev = ((length - 1) * prev + true_ranges[i]) / length
        out[i] = prev
    return out
