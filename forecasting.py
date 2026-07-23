"""
main.py ve app.py tarafından ortak kullanılan model eğitim/tahmin fonksiyonları.
Kod tekrarını önlemek için forecast.py'deki mantık buraya taşındı.
"""
import os
import warnings

import numpy as np
import pandas as pd
from prophet import Prophet
from sklearn.metrics import mean_absolute_error, mean_squared_error
from statsmodels.tsa.arima.model import ARIMA

TEST_SIZE = 30  # backtest için ayrılan son gün sayısı
FORECAST_HORIZON_DAYS = 90  # ileriye dönük kaç takvim günü tahmin edilecek

# TCMB EVDS'teki "Doviz Kurlari" veri grubunda (bie_dkdovytl) yayinlanan ve
# halen guncel tutulan alis kuru serileri. BGN ve IRR artik guncellenmedigi,
# euro-oncesi ulusal para birimleri (DEM, FRF, ITL, vb.) ve ECU 2002'den
# beri pasif oldugu, XDR (IMF Ozel Cekme Hakki) gercek bir doviz olmadigi
# ve KZT/TRY icin yeterli veri gecmisi olmadigi (~150 satir) icin listeye
# alinmadi.
#
# NOK, KRW ve RUB'un gunluk oynakligi digerlerinden yuksek, bu yuzden
# tahmin hatalari da nispeten yuksek; yine de yeterli veri gecmisine sahip
# olduklari icin listede tutuluyorlar.
CURRENCY_SERIES = {
    "USD": "TP.DK.USD.A",
    "EUR": "TP.DK.EUR.A",
    "GBP": "TP.DK.GBP.A",
    "CHF": "TP.DK.CHF.A",
    "AUD": "TP.DK.AUD.A",
    "CAD": "TP.DK.CAD.A",
    "DKK": "TP.DK.DKK.A",
    "SEK": "TP.DK.SEK.A",
    "NOK": "TP.DK.NOK.A",
    "JPY": "TP.DK.JPY.A",
    "CNY": "TP.DK.CNY.A",
    "KRW": "TP.DK.KRW.A",
    "AED": "TP.DK.AED.A",
    "SAR": "TP.DK.SAR.A",
    "QAR": "TP.DK.QAR.A",
    "KWD": "TP.DK.KWD.A",
    "AZN": "TP.DK.AZN.A",
    "PKR": "TP.DK.PKR.A",
    "RON": "TP.DK.RON.A",
    "RUB": "TP.DK.RUB.A",
}

CURRENCY_NAMES = {
    "USD": "ABD Doları",
    "EUR": "Euro",
    "GBP": "İngiliz Sterlini",
    "CHF": "İsviçre Frangı",
    "AUD": "Avustralya Doları",
    "CAD": "Kanada Doları",
    "DKK": "Danimarka Kronu",
    "SEK": "İsveç Kronu",
    "NOK": "Norveç Kronu",
    "JPY": "Japon Yeni (100)",
    "CNY": "Çin Yuanı",
    "KRW": "Güney Kore Wonu",
    "AED": "BAE Dirhemi",
    "SAR": "Suudi Arabistan Riyali",
    "QAR": "Katar Riyali",
    "KWD": "Kuveyt Dinarı",
    "AZN": "Azerbaycan Manatı",
    "PKR": "Pakistan Rupisi",
    "RON": "Rumen Leyi",
    "RUB": "Rus Rublesi",
}


# Tum uretilen veri/tahmin/metrik dosyalari data/ altinda toplanir, kod
# dosyalarindan (main.py, forecasting.py, ...) ayri tutulur. Bu ucu de
# repo kokunde 60+ dosya birikmesini onlemek icin var - baska hicbir yerde
# dosya yolu hardcode edilmemeli, hep bu fonksiyonlar cagrilmali.
DATA_DIR = "data"

os.makedirs(f"{DATA_DIR}/raw", exist_ok=True)
os.makedirs(f"{DATA_DIR}/forecasts", exist_ok=True)
os.makedirs(f"{DATA_DIR}/metrics", exist_ok=True)
os.makedirs(f"{DATA_DIR}/forecast_history", exist_ok=True)
os.makedirs(f"{DATA_DIR}/accuracy", exist_ok=True)


def data_path(code):
    return f"{DATA_DIR}/raw/{code.lower()}_try_data.csv"


def forecast_path(code):
    return f"{DATA_DIR}/forecasts/forecast_{code.lower()}.csv"


def metrics_path(code):
    return f"{DATA_DIR}/metrics/metrics_{code.lower()}.json"


def model_comparison_path():
    return f"{DATA_DIR}/model_comparison.json"


def forecast_history_path(code):
    """forecast.py'nin her calistirmada biriktirdigi gecmis tahmin
    anlik goruntulerinin (generated_on/ds/yhat/...) tutuldugu dosya.
    accuracy.py bunu gercek kurla karsilastirip gecmis isabet oranini hesaplar."""
    return f"{DATA_DIR}/forecast_history/history_{code.lower()}.csv"


def accuracy_path(code):
    return f"{DATA_DIR}/accuracy/accuracy_{code.lower()}.json"

# Modeller sadece son N gunluk veriyle egitilir. Cok daha eski, artik
# gecerli olmayan trendlerin (ornegin gecmis kriz donemlerindeki sert
# hareketlerin) guncel tahminleri carpitmasini onler; ayni zamanda yillik
# mevsimsellik icin yeterli veriyi korur.
TRAIN_WINDOW_DAYS = 730


def load_series(csv_path):
    """<currency>_try_data.csv dosyasını Prophet'in beklediği ds/y kolonlarıyla okur."""
    df = pd.read_csv(csv_path)
    df = df.rename(columns={"date": "ds", "rate": "y"})
    df["ds"] = pd.to_datetime(df["ds"])
    return df


# Prophet'in varsayilan changepoint_range=0.8 degeri, egitim verisinin son
# %20'lik diliminde yeni bir trend kirilmasi aramaz; bu, yakin donemde
# olusan gercek bir trend degisikligini kacirabilir. Daha yuksek bir deger
# bunu duzeltebilir ama her para biriminde iyilestirmez; bu yuzden
# select_best_model bu degerleri ARIMA ile birlikte aday olarak deneyip en
# dusuk backtest hatasini verenini seciyor.
PROPHET_CHANGEPOINT_RANGES = [0.8, 0.9, 0.95]


def train_prophet(train_df, changepoint_range=0.8):
    # Haftalik/yillik mevsimsellik kapali: FX kurlarinda gercek bir haftalik
    # donguye dayanak yok (hafta sonu bosluklarindan kaynaklanan gurultuyu
    # ogreniyor), ve sadece 2 yillik veriyle yillik mevsimsellik guvenilir
    # kestirilemiyor. Kapatmak, trend bilesenini (asil sinyal) one cikariyor.
    model = Prophet(
        yearly_seasonality=False,
        weekly_seasonality=False,
        changepoint_range=changepoint_range,
    )
    model.fit(train_df)
    return model


def _limit_window(df, window_days=TRAIN_WINDOW_DAYS):
    """Sadece en son tarihten geriye `window_days` günlük veriyi tutar."""
    cutoff = df["ds"].max() - pd.Timedelta(days=window_days)
    return df[df["ds"] >= cutoff].reset_index(drop=True)


def evaluate_holdout(df, test_size=TEST_SIZE, changepoint_range=0.8):
    """Son `test_size` satırı test için ayırır, geri kalanın son TRAIN_WINDOW_DAYS
    günüyle eğitir ve karşılaştırır."""
    train_df = _limit_window(df[:-test_size])
    test_df = df[-test_size:]

    model = train_prophet(train_df, changepoint_range=changepoint_range)
    # İş günü olmayan günleri de kapsasın diye birkaç gün fazladan tahmin et
    future = model.make_future_dataframe(periods=test_size + 15)
    forecast = model.predict(future)

    comparison = test_df[["ds", "y"]].merge(forecast[["ds", "yhat"]], on="ds")
    comparison["error"] = comparison["y"] - comparison["yhat"]

    mae = mean_absolute_error(comparison["y"], comparison["yhat"])
    rmse = np.sqrt(mean_squared_error(comparison["y"], comparison["yhat"]))
    mape = (abs(comparison["error"]) / comparison["y"]).mean() * 100

    return {
        "mae": float(mae),
        "rmse": float(rmse),
        "mape": float(mape),
        "test_size": int(len(comparison)),
    }


# ARIMA icin denenecek (p,d,q) kombinasyonlari. d=1 sabit: kur serileri
# duraganlik testinden gecmiyor (birim kok var), farkini almak gerekiyor.
# p ve q 0-3 arasinda araniyor; daha yuksek dereceler asiri uydurma
# riskini artiracagi icin sinirli tutuluyor.
ARIMA_ORDER_SEARCH = [(p, 1, q) for p in range(4) for q in range(4)]


def evaluate_arima_holdout(df, test_size=TEST_SIZE):
    """Prophet ile adil karsilastirma icin AYNI train/test bolunmesini
    (_limit_window ile son TRAIN_WINDOW_DAYS gun) kullanir. Birkac (p,d,q)
    kombinasyonunu egitim verisindeki AIC'ye gore dener, en iyisini secip
    onunla test donemini tahmin eder."""
    train_df = _limit_window(df[:-test_size])
    test_df = df[-test_size:]
    y_train = train_df["y"].to_numpy()
    y_test = test_df["y"].to_numpy()

    best_aic, best_order, best_result = np.inf, None, None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for order in ARIMA_ORDER_SEARCH:
            try:
                result = ARIMA(y_train, order=order).fit()
            except Exception:
                continue
            if result.aic < best_aic:
                best_aic, best_order, best_result = result.aic, order, result

    forecast = best_result.forecast(steps=test_size)
    mae = mean_absolute_error(y_test, forecast)
    rmse = np.sqrt(mean_squared_error(y_test, forecast))
    mape = (np.abs(y_test - forecast) / y_test).mean() * 100

    return {
        "mae": float(mae),
        "rmse": float(rmse),
        "mape": float(mape),
        "test_size": int(test_size),
        "order": list(best_order),
    }


def forecast_future(df, periods=FORECAST_HORIZON_DAYS, changepoint_range=0.8):
    """Son TRAIN_WINDOW_DAYS günlük veriyle yeniden eğitip bugünden itibaren
    ileriye dönük tahmin üretir."""
    train_df = _limit_window(df)
    model = train_prophet(train_df, changepoint_range=changepoint_range)
    future = model.make_future_dataframe(periods=periods)
    forecast = model.predict(future)
    future_only = forecast[forecast["ds"] > train_df["ds"].max()]
    return future_only[["ds", "yhat", "yhat_lower", "yhat_upper"]].reset_index(drop=True)


def forecast_future_arima(df, periods=FORECAST_HORIZON_DAYS):
    """forecast_future'in ARIMA karsiligi: ayni cikti semasini (ds/yhat/
    yhat_lower/yhat_upper) uretir ki app.py hangi modelin sectigini bilmek
    zorunda kalmasin. ARIMA is gunu (haftasonu olmayan) bazinda tahmin
    urettigi icin, `periods` takvim gunune denk gelen is gunu sayisi kadar
    adim ileri tahmin edip bu is gunlerine tarih olarak atar."""
    train_df = _limit_window(df)
    y_train = train_df["y"].to_numpy()

    best_aic, best_order, best_result = np.inf, None, None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for order in ARIMA_ORDER_SEARCH:
            try:
                result = ARIMA(y_train, order=order).fit()
            except Exception:
                continue
            if result.aic < best_aic:
                best_aic, best_order, best_result = result.aic, order, result

    calendar_days = pd.date_range(start=train_df["ds"].max() + pd.Timedelta(days=1), periods=periods, freq="D")
    business_days = calendar_days[calendar_days.dayofweek < 5]

    forecast = best_result.get_forecast(steps=len(business_days))
    summary = forecast.summary_frame(alpha=0.05)

    return pd.DataFrame(
        {
            "ds": business_days,
            "yhat": summary["mean"].to_numpy(),
            "yhat_lower": summary["mean_ci_lower"].to_numpy(),
            "yhat_upper": summary["mean_ci_upper"].to_numpy(),
        }
    )


def select_best_model(df, test_size=TEST_SIZE):
    """Prophet'i birkac changepoint_range degeriyle ve ARIMA'yi ayni
    backtest'te karsilastirip en dusuk MAPE'yi verenini secer. Hangi
    modelin daha isabetli oldugu para birimine gore degistigi icin secim
    her doviz icin ayri ayri yapilir."""
    candidates = []
    for cr in PROPHET_CHANGEPOINT_RANGES:
        metrics = evaluate_holdout(df, test_size=test_size, changepoint_range=cr)
        candidates.append(("prophet", cr, metrics))

    arima_metrics = evaluate_arima_holdout(df, test_size=test_size)
    candidates.append(("arima", None, arima_metrics))

    chosen_type, chosen_cr, chosen_metrics = min(candidates, key=lambda c: c[2]["mape"])
    best_prophet_mape = min(m["mape"] for kind, _, m in candidates if kind == "prophet")
    alternative_mape = arima_metrics["mape"] if chosen_type == "prophet" else best_prophet_mape

    return {
        "model": chosen_type,
        "mae": chosen_metrics["mae"],
        "rmse": chosen_metrics["rmse"],
        "mape": chosen_metrics["mape"],
        "test_size": chosen_metrics["test_size"],
        "changepoint_range": chosen_cr,
        "arima_order": arima_metrics["order"] if chosen_type == "arima" else None,
        "alternative_model": "arima" if chosen_type == "prophet" else "prophet",
        "alternative_mape": alternative_mape,
    }


def forecast_future_best(df, model, changepoint_range=0.8, periods=FORECAST_HORIZON_DAYS):
    """select_best_model'in sectigi modele (ve Prophet ise
    changepoint_range'e) gore uygun forecast_future* fonksiyonunu cagirir."""
    if model == "arima":
        return forecast_future_arima(df, periods=periods)
    return forecast_future(df, periods=periods, changepoint_range=changepoint_range)
