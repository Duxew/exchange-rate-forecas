"""
CURRENCY_SERIES icindeki her doviz icin:
  1) Prophet'i PROPHET_CHANGEPOINT_RANGES'teki her degerle ve ARIMA'yi ayni
     backtest'te (son 30 is gunu test, onceki TRAIN_WINDOW_DAYS gun egitim)
     karsilastirir, en dusuk MAPE'yi verenini secer (forecasting.select_best_model)
     ve secilen modelin metriklerini data/metrics/metrics_<currency>.json
     dosyasina kaydeder.
  2) Secilen model/konfigurasyonla yeniden egitip bugunden itibaren ileriye
     donuk tahmin uretir ve data/forecasts/forecast_<currency>.csv dosyasina
     kaydeder. Prophet ve ARIMA ayni ds/yhat/yhat_lower/yhat_upper semasini
     urettigi icin app.py hangi modelin kullanildigini bilmek zorunda degil.

app.py bu forecast_*.csv ve metrics_*.json dosyalarini okuyarak calisir; bu
yuzden veri guncellendiginde (main.py) bu script de yeniden calistirilmalidir:

    .venv\\Scripts\\python.exe main.py
    .venv\\Scripts\\python.exe forecast.py
"""
import json

from forecasting import (
    CURRENCY_SERIES,
    TEST_SIZE,
    TRAIN_WINDOW_DAYS,
    data_path,
    forecast_future_best,
    forecast_path,
    load_series,
    metrics_path,
    select_best_model,
)


def main():
    for code in CURRENCY_SERIES:
        print(f"\n=== {code}/TRY ===")
        df = load_series(data_path(code))

        # 1) Prophet (birkac changepoint_range ile) vs ARIMA karsilastir, kazanani sec
        print(f"Testing on last {TEST_SIZE} days, training on the {TRAIN_WINDOW_DAYS} days before that")
        metrics = select_best_model(df)
        if metrics["model"] == "arima":
            detail = f" order={tuple(metrics['arima_order'])}"
        else:
            detail = f" changepoint_range={metrics['changepoint_range']}"
        print(f"Secilen model: {metrics['model'].upper()}{detail}")
        print(f"MAE (Mean Absolute Error): {metrics['mae']:.4f} TRY")
        print(f"RMSE (Root Mean Squared Error): {metrics['rmse']:.4f} TRY")
        print(f"MAPE (Mean Absolute Percentage Error): {metrics['mape']:.2f}%  (diger model: {metrics['alternative_model'].upper()} %{metrics['alternative_mape']:.2f})")

        with open(metrics_path(code), "w") as f:
            json.dump(metrics, f, indent=2)
        print(f"Metrics saved to {metrics_path(code)}")

        # 2) Secilen modelle (ve Prophet ise kazanan changepoint_range'le) yeniden
        # egit, ileriye donuk tahmin uret (app.py bunu kullanir)
        future_forecast = forecast_future_best(
            df, metrics["model"], changepoint_range=metrics["changepoint_range"] or 0.8
        )
        future_forecast.to_csv(forecast_path(code), index=False)
        print(f"Forecast saved to {forecast_path(code)} ({len(future_forecast)} days)")


if __name__ == "__main__":
    # Bazi kutuphaneler Windows'ta multiprocessing "spawn" ile bu dosyayi
    # tekrar import edebiliyor; guard olmadan bu, scriptin ikinci kez
    # calisip ayni dosyalara yazmasina yol acabilir.
    main()
