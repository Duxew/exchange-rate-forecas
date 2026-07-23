"""
forecast.py'nin her calistirmada data/forecast_history/history_<currency>.csv
dosyasina biriktirdigi gecmis tahminleri, artik gerceklesmis olan gercek kurla
(data/raw/<currency>_try_data.csv) karsilastirir.

Her doviz icin, gercegi artik bilinen (ds <= bugun) her gecmis tahmin satirinin
hatasini hesaplar, tahminin ne kadar ileriye bakarak uretildigine gore
(horizon_days = ds - generated_on) 1-7 / 8-30 / 31-90 gunluk kovalara ayirir ve
her kova + genel icin MAE/RMSE/MAPE'yi data/accuracy/accuracy_<currency>.json
dosyasina yazar.

Henuz hic gecmis birikmemis (history dosyasi yok) ya da gercegi bilinen hicbir
satiri olmayan (butun tahminler hala gelecekte) dovizler icin dosya yazilmaz -
app.py bu durumu "yeterli gecmis yok" mesajiyla gosterir.

    .venv\\Scripts\\python.exe accuracy.py

main.py -> forecast.py -> accuracy.py sirasiyla calistirilmali (accuracy.py,
forecast.py'nin biriktirdigi history'e ve main.py'nin guncel raw verisine
ihtiyac duyar). GitHub Actions bu zinciri gunluk otomatik calistirir.
"""
import json
import os

import numpy as np
import pandas as pd

from forecasting import CURRENCY_SERIES, accuracy_path, data_path, forecast_history_path, load_series

HORIZON_BUCKETS = [
    ("1-7", 1, 7),
    ("8-30", 8, 30),
    ("31-90", 31, 90),
]


def _bucket_metrics(comparison):
    mae = float((comparison["error"].abs()).mean())
    rmse = float(np.sqrt((comparison["error"] ** 2).mean()))
    mape = float((comparison["error"].abs() / comparison["y"]).mean() * 100)
    return {"mae": mae, "rmse": rmse, "mape": mape, "n_observations": int(len(comparison))}


def compute_accuracy(code):
    history_path = forecast_history_path(code)
    if not os.path.exists(history_path):
        return None

    history = pd.read_csv(history_path, parse_dates=["generated_on", "ds"])
    actual = load_series(data_path(code))[["ds", "y"]]

    comparison = history.merge(actual, on="ds", how="inner")
    if comparison.empty:
        return None

    comparison["error"] = comparison["y"] - comparison["yhat"]
    comparison["horizon_days"] = (comparison["ds"] - comparison["generated_on"]).dt.days
    # Ayni gecmis tahmin, farkli generated_on'lardan tekrar uretilmis olabilir
    # (ornegin her gun eklenen bir sonraki gunun tahmini); en yakin zamanda
    # uretilmis (en kucuk horizon) tahmini tutuyoruz ki her gercek gozlem
    # birden fazla kez sayilmasin.
    comparison = comparison.sort_values("horizon_days").drop_duplicates(subset="ds", keep="first")

    by_horizon = {}
    for label, lo, hi in HORIZON_BUCKETS:
        bucket = comparison[(comparison["horizon_days"] >= lo) & (comparison["horizon_days"] <= hi)]
        if not bucket.empty:
            by_horizon[label] = _bucket_metrics(bucket)

    overall = _bucket_metrics(comparison)

    return {
        "currency": code,
        "n_observations": overall["n_observations"],
        "overall_mae": overall["mae"],
        "overall_rmse": overall["rmse"],
        "overall_mape": overall["mape"],
        "by_horizon": by_horizon,
        "last_updated": pd.Timestamp.today().date().isoformat(),
    }


def main():
    for code in CURRENCY_SERIES:
        result = compute_accuracy(code)
        if result is None:
            print(f"{code}: henuz gercegi bilinen bir gecmis tahmin yok, atlandi")
            continue

        with open(accuracy_path(code), "w") as f:
            json.dump(result, f, indent=2)
        print(
            f"{code}: {result['n_observations']} gozlem, "
            f"genel MAPE=%{result['overall_mape']:.2f} -> {accuracy_path(code)}"
        )


if __name__ == "__main__":
    main()
