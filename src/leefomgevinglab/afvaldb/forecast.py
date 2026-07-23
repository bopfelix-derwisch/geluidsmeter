"""Holt's lineaire exponential smoothing (zelf-geïmplementeerd, numpy).

Indicatieve modelmatige extrapolatie — geen beleidsprognose.
"""
import numpy as np

from leefomgevinglab.afvaldb import store

MIN_PUNTEN = 5


def _holt_sse(y, alpha, beta):
    level, trend = y[0], y[1] - y[0]
    sse = 0.0
    resid = []
    for t in range(1, len(y)):
        voorspeld = level + trend
        fout = y[t] - voorspeld
        sse += fout * fout
        resid.append(fout)
        level_prev = level
        level = alpha * y[t] + (1 - alpha) * (level + trend)
        trend = beta * (level - level_prev) + (1 - beta) * trend
    return sse, level, trend, resid


def fit_holt(y: list[float]) -> dict:
    y = [float(v) for v in y]
    best = None
    for alpha in np.linspace(0.1, 0.9, 9):
        for beta in np.linspace(0.1, 0.9, 9):
            sse, level, trend, resid = _holt_sse(y, alpha, beta)
            if best is None or sse < best[0]:
                best = (sse, alpha, beta, level, trend, resid)
    sse, alpha, beta, level, trend, resid = best
    resid_std = float(np.std(resid)) if resid else 0.0
    return {"alpha": float(alpha), "beta": float(beta), "level": float(level),
            "trend": float(trend), "resid_std": resid_std}


def forecast_holt(jaren: list[int], y: list[float], tot_jaar: int, z: float = 1.28) -> list[dict]:
    if len(y) < MIN_PUNTEN:
        return []
    f = fit_holt(y)
    laatste = int(jaren[-1])
    out = []
    for h, jaar in enumerate(range(laatste + 1, tot_jaar + 1), start=1):
        verwacht = f["level"] + h * f["trend"]
        band = z * f["resid_std"] * (h ** 0.5)
        out.append({"jaar": jaar, "verwacht": verwacht,
                    "ondergrens": max(0.0, verwacht - band), "bovengrens": verwacht + band})
    return out


def bouw_forecasts(con, tot_jaar: int = 2035) -> int:
    combos = con.execute(
        "SELECT DISTINCT regio_code, afvalstroom_canoniek FROM afval_feit "
        "WHERE indicator_type = 'volume'").fetchall()
    n = 0
    for regio, stroom in combos:
        reeks = store.series(con, regio, stroom, indicator_type="volume")
        if len(reeks) < MIN_PUNTEN:
            continue
        jaren = [j for j, _ in reeks]
        y = [v for _, v in reeks]
        rows = forecast_holt(jaren, y, tot_jaar)
        if not rows:
            continue
        store.insert_forecasts(con, [{"regio_code": regio, "afvalstroom_canoniek": stroom,
                                      "jaar": r["jaar"], "verwacht": r["verwacht"],
                                      "ondergrens": r["ondergrens"], "bovengrens": r["bovengrens"],
                                      "methode": "holt"} for r in rows])
        n += 1
    return n
