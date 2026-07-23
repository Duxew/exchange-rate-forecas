"""
Doviz bazli urun fiyatlandirma araci.

Kullanici; miktar, birim fiyat (doviz cinsinden) ve odeme/teslim tarihi girer.
Uygulama, guncel kuru ve secilen modelin (Prophet veya ARIMA) ilgili tarih icin
urettigi tahmin araligini (yhat_lower / yhat / yhat_upper) kullanarak onerilen
teklif fiyatini, kur riski payini ve tahmin araligini hesaplar.

Bu uygulama forecast.py/accuracy.py tarafindan onceden uretilmis dosyalari okur
(modeli her seferinde yeniden egitmek yavas oldugu icin). Once su scriptleri
calistirmis olmak gerekir:

    .venv\\Scripts\\python.exe main.py
    .venv\\Scripts\\python.exe forecast.py
    .venv\\Scripts\\python.exe accuracy.py

Calistirmak icin:
    .venv\\Scripts\\python.exe -m streamlit run app.py
"""
import json
from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from forecasting import (
    CURRENCY_NAMES,
    CURRENCY_SERIES,
    accuracy_path,
    data_path,
    forecast_history_path,
    forecast_path,
    metrics_path,
)

HISTORY_DISPLAY_DAYS = 180  # grafikte gosterilecek gecmis veri uzunlugu

# ONERI_DOKUMANI.md'deki guven tablosuyla birebir ayni esik (%1 alti = yuksek guven).
HIGH_CONFIDENCE_MAPE_THRESHOLD = 1.0

# dataviz referans paletinin kategorik 1. (mavi) ve 2. (turuncu) slotlari.
COLOR_HISTORY = "#2a78d6"
COLOR_FORECAST = "#eb6834"

st.set_page_config(
    page_title="Döviz Bazlı Fiyatlandırma",
    page_icon=":material/currency_exchange:",
)

CURRENCIES = {
    code: {
        "data": data_path(code),
        "forecast": forecast_path(code),
        "metrics": metrics_path(code),
        "accuracy": accuracy_path(code),
        "forecast_history": forecast_history_path(code),
    }
    for code in CURRENCY_SERIES
}


@st.cache_data
def load_history(data_path):
    return pd.read_csv(data_path, parse_dates=["date"])


@st.cache_data
def load_current_rate(data_path):
    df = load_history(data_path)
    last_row = df.iloc[-1]
    return float(last_row["rate"]), last_row["date"]


@st.cache_data
def load_forecast(forecast_path):
    return pd.read_csv(forecast_path, parse_dates=["ds"])


@st.cache_data
def load_metrics(metrics_path):
    with open(metrics_path) as f:
        return json.load(f)


@st.cache_data
def load_accuracy(accuracy_path):
    with open(accuracy_path) as f:
        return json.load(f)


st.title("Döviz Bazlı Ürün Fiyatlandırma")
st.caption(
    "TCMB EVDS'in yayınladığı tüm aktif döviz kurları için tahmin modeline "
    "dayalı fiyatlandırma ve kur riski aracı."
)

col1, col2 = st.columns(2)
with col1:
    currency = st.selectbox(
        "Döviz cinsi",
        list(CURRENCIES.keys()),
        format_func=lambda code: f"{code} - {CURRENCY_NAMES.get(code, code)}",
    )
with col2:
    quantity = st.number_input("Ürün miktarı (adet)", min_value=1, value=100, step=1)

unit_price = st.number_input(
    f"Birim fiyat ({currency})", min_value=0.0, value=10.0, step=0.5
)

paths = CURRENCIES[currency]
try:
    current_rate, current_rate_date = load_current_rate(paths["data"])
    forecast_df = load_forecast(paths["forecast"])
    metrics = load_metrics(paths["metrics"])
except FileNotFoundError as e:
    st.error(
        f"Gerekli veri dosyası bulunamadı: {e.filename}\n\n"
        f"{currency} için önce terminalde sırasıyla şu scriptleri çalıştırın:\n"
        "1) `python main.py`\n2) `python forecast.py`"
    )
    st.stop()

min_date = forecast_df["ds"].min().date()
max_date = forecast_df["ds"].max().date()
default_target = min(date.today() + timedelta(days=30), max_date)

target_date = st.date_input(
    "Ödeme / teslim tarihi",
    value=default_target,
    min_value=min_date,
    max_value=max_date,
)

# Secilen tarih hafta sonuna denk gelebilir; en yakin tahmini bul.
forecast_df["day_diff"] = (forecast_df["ds"].dt.date - target_date).abs()
closest = forecast_df.loc[forecast_df["day_diff"].idxmin()]

foreign_amount = quantity * unit_price
current_price_try = foreign_amount * current_rate
expected_price_try = foreign_amount * closest["yhat"]
low_price_try = foreign_amount * closest["yhat_lower"]
high_price_try = foreign_amount * closest["yhat_upper"]

# Model ust sinirin altinda bir kur da ongorebilir (kur dususu bekleniyor demektir).
# Ham payi (negatif olabilir) hala hesaplayip gosteriyoruz, ama onerilen teklif
# fiyatina sadece pozitifse ekliyoruz - bkz. asagidaki recommended_price_try.
risk_try = high_price_try - current_price_try
risk_pct = (closest["yhat_upper"] - current_rate) / current_rate * 100

# ONERI_DOKUMANI.md'nin onerdigi fiyatlandirma kurali: "guncel kura gore fiyat +
# kur riski payi". Model dusus ongoruyorsa (risk_try negatif) fiyati asagi
# cekmek yerine guncel fiyatta birakiyoruz - dokumanin "teklif yine de temkinli
# verilmeli" notuyla tutarli.
recommended_price_try = current_price_try + max(risk_try, 0)

tab_teklif, tab_grafik, tab_detay = st.tabs(["Teklif", "Grafik", "Model Detayları"])

with tab_teklif:
    with st.container(border=True):
        st.caption("Önerilen teklif fiyatı")
        st.markdown(
            f"<div style='font-size:3rem;font-weight:700;line-height:1.15'>"
            f"{recommended_price_try:,.2f} TRY</div>",
            unsafe_allow_html=True,
        )
        if risk_try > 0:
            st.write(
                f"Güncel fiyatın üzerine %{risk_pct:.2f} kur riski payı eklendi "
                f"(+{risk_try:,.2f} TRY)."
            )
        else:
            st.write("Model bir düşüş öngörüyor, ek bir güvenlik payına gerek görülmedi.")

        if metrics["mape"] < HIGH_CONFIDENCE_MAPE_THRESHOLD:
            st.badge("Güven: Yüksek", icon=":material/check_circle:", color="green")
        else:
            st.badge("Güven: Orta", icon=":material/error:", color="orange")

    st.write("")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.caption(f"Güncel kur ({current_rate_date.date()})")
        st.write(f"{current_rate:.4f} TRY")
    with c2:
        st.caption("Güncel fiyat")
        st.write(f"{current_price_try:,.2f} TRY")
    with c3:
        st.caption(f"Tahmini aralık ({closest['ds'].date()})")
        st.write(f"{low_price_try:,.2f} – {high_price_try:,.2f} TRY")

with tab_grafik:
    with st.container(border=True):
        history_df = load_history(paths["data"])
        recent_history = history_df[
            history_df["date"] >= history_df["date"].max() - pd.Timedelta(days=HISTORY_DISPLAY_DAYS)
        ]

        # Egilimin daha net gorunmesi icin y eksenini 0'dan degil, verinin
        # araligindan baslatiyoruz (alt.Scale(zero=False)).
        y_min = min(recent_history["rate"].min(), forecast_df["yhat_lower"].min())
        y_max = max(recent_history["rate"].max(), forecast_df["yhat_upper"].max())
        y_scale = alt.Scale(domain=[y_min * 0.98, y_max * 1.02], zero=False)

        band = (
            alt.Chart(forecast_df)
            .mark_area(opacity=0.15, color=COLOR_FORECAST)
            .encode(
                x=alt.X("ds:T", title="Tarih"),
                y=alt.Y("yhat_lower:Q", title=f"{currency}/TRY", scale=y_scale),
                y2="yhat_upper:Q",
            )
        )
        forecast_line = (
            alt.Chart(forecast_df)
            .mark_line(color=COLOR_FORECAST, strokeWidth=2, strokeDash=[5, 3])
            .encode(x="ds:T", y=alt.Y("yhat:Q", scale=y_scale), tooltip=["ds:T", "yhat:Q"])
        )
        history_line = (
            alt.Chart(recent_history)
            .mark_line(color=COLOR_HISTORY, strokeWidth=2)
            .encode(x="date:T", y=alt.Y("rate:Q", scale=y_scale), tooltip=["date:T", "rate:Q"])
        )
        target_rule = (
            alt.Chart(pd.DataFrame({"d": [pd.Timestamp(target_date)]}))
            .mark_rule(color=COLOR_FORECAST, strokeDash=[2, 2])
            .encode(x="d:T")
        )

        chart = (band + history_line + forecast_line + target_rule).properties(height=380).interactive()
        st.altair_chart(chart, use_container_width=True)
        st.caption(
            "Mavi çizgi: gerçekleşen kur (son "
            f"{HISTORY_DISPLAY_DAYS} gün). Turuncu kesikli çizgi: tahmin (yhat), turuncu "
            "bant: belirsizlik aralığı (yhat_lower–yhat_upper). Dikey kesikli çizgi: "
            "seçilen ödeme/teslim tarihi."
        )

with tab_detay:
    st.subheader("Backtest metrikleri")
    st.caption(
        f"Model: {metrics['model'].upper()} ({currency}/TRY, son "
        f"{metrics['test_size']} iş günü backtest)"
    )
    d1, d2, d3 = st.columns(3)
    d1.metric("MAE", f"{metrics['mae']:.4f} TRY")
    d2.metric("RMSE", f"{metrics['rmse']:.4f} TRY")
    d3.metric("MAPE", f"%{metrics['mape']:.2f}")

    st.divider()
    st.subheader("Model doğruluk geçmişi")

    try:
        accuracy = load_accuracy(paths["accuracy"])
    except FileNotFoundError:
        st.info(
            "Bu döviz için henüz yeterli geçmiş tahmin verisi birikmedi. "
            "Otomatik günlük yenileme başladıktan bir süre sonra (tahminlerin "
            "hedeflediği tarihler gerçekleştikçe) burada gerçekleşen isabet oranı "
            "görünecek."
        )
    else:
        st.caption(
            f"Geçmişte üretilen tahminlerin, hedefledikleri tarih gerçekleştikten sonra "
            f"gerçek kurla karşılaştırılmasına dayanır ({accuracy['n_observations']} "
            f"gözlem, son güncelleme: {accuracy['last_updated']})."
        )
        a1, a2, a3 = st.columns(3)
        a1.metric("Gerçekleşen MAPE (genel)", f"%{accuracy['overall_mape']:.2f}")
        a2.metric("Gerçekleşen MAE", f"{accuracy['overall_mae']:.4f} TRY")
        a3.metric("Gerçekleşen RMSE", f"{accuracy['overall_rmse']:.4f} TRY")

        by_horizon = accuracy["by_horizon"]
        if by_horizon:
            horizon_df = pd.DataFrame(
                [
                    {"Ufuk (gün)": label, "MAPE (%)": vals["mape"], "Gözlem": vals["n_observations"]}
                    for label, vals in by_horizon.items()
                ]
            )
            horizon_chart = (
                alt.Chart(horizon_df)
                .mark_bar(color=COLOR_HISTORY)
                .encode(
                    x=alt.X("Ufuk (gün):N", sort=None),
                    y=alt.Y("MAPE (%):Q"),
                    tooltip=["Ufuk (gün)", "MAPE (%)", "Gözlem"],
                )
                .properties(height=220)
            )
            st.altair_chart(horizon_chart, use_container_width=True)
            st.caption(
                "Tahmin üretildikten kaç gün sonrasını hedeflediğine göre gruplanmış "
                "gerçekleşen MAPE (kısa ufuk genelde daha isabetlidir)."
            )
