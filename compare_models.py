"""
Prophet ile ARIMA'yi ayni backtest bolunmeleri uzerinde, 7/30/90 gunluk
ufuklarda karsilastirir ve sonuclari data/model_comparison.json dosyasina
kaydeder. forecast.py'nin kullandigi tek-ufuklu (30 gun) secimden daha
kapsamli, belgeleme amacli bir karsilastirmadir.

Ikisi de HER ufuk icin AYNI train/test bolunmesini kullanir
(forecasting._limit_window ile son TRAIN_WINDOW_DAYS gun egitim, son
`horizon` gun test), bu yuzden sonuclar dogrudan karsilastirilabilir.

Calistirmadan once main.py ve forecast.py calismis olmali (veri dosyalari
icin). Calistirmak icin:

    .venv\\Scripts\\python.exe compare_models.py
"""
import json

from forecasting import (
    CURRENCY_SERIES,
    data_path,
    evaluate_arima_holdout,
    evaluate_holdout,
    load_series,
    model_comparison_path,
)

# Uygulamanin (app.py) destekledigi odeme/teslim tarihi araligi 1-90 gun
# oldugu icin bu uc ufku test ediyoruz: kisa (7), orta (30, backtest'te
# kullanilan standart TEST_SIZE), uzun (90, FORECAST_HORIZON_DAYS ile ayni).
HORIZONS = [7, 30, 90]


def main():
    results = {}

    for code in CURRENCY_SERIES:
        print(f"\n=== {code}/TRY ===")
        df = load_series(data_path(code))
        results[code] = {"horizons": {}}

        print(f"{'Ufuk':>6s}  {'Prophet MAPE':>13s}  {'ARIMA MAPE':>11s}  {'ARIMA order':>12s}  Kazanan")
        for horizon in HORIZONS:
            prophet_metrics = evaluate_holdout(df, test_size=horizon)
            arima_metrics = evaluate_arima_holdout(df, test_size=horizon)
            winner = "ARIMA" if arima_metrics["mape"] < prophet_metrics["mape"] else "Prophet"

            print(
                f"{horizon:>4d}g  {prophet_metrics['mape']:12.2f}%  {arima_metrics['mape']:10.2f}%  "
                f"{str(tuple(arima_metrics['order'])):>12s}  {winner}"
            )

            results[code]["horizons"][str(horizon)] = {
                "prophet": prophet_metrics,
                "arima": arima_metrics,
                "winner": winner,
            }

        # Uygulamanin standart backtest ufku (TEST_SIZE=30) resmi karsilastirma
        # olarak isaretleniyor - forecast.py'deki metrics_<code>.json ile ayni
        # ufuktur, dogrudan karsilastirilabilir.
        official = results[code]["horizons"]["30"]
        results[code]["official_winner"] = official["winner"]
        print(f"-> Resmi (30 gun) karsilastirmada kazanan: {official['winner']}")

    with open(model_comparison_path(), "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nKarsilastirma sonuclari {model_comparison_path()} dosyasina kaydedildi.")

    print(
        "\nNot: app.py, hangi modelin (Prophet/ARIMA) kullanilacagina her\n"
        "doviz icin forecast.py > forecasting.select_best_model uzerinden\n"
        "ayri ayri karar veriyor. Bu script sadece daha kapsamli bir\n"
        "karsilastirma/belgeleme araci; app.py'nin gercekte hangi modeli\n"
        "kullandigini gormek icin metrics_<kod>.json > model alanina bak."
    )


if __name__ == "__main__":
    # Bazi kutuphaneler Windows'ta multiprocessing "spawn" ile bu dosyayi
    # tekrar import edebiliyor; guard olmadan bu, scriptin ikinci kez
    # calisip ayni dosyaya yazmasina yol acabilir.
    main()
