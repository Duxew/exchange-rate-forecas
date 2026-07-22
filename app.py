"""
Doviz bazli urun fiyatlandirma araci.

Kullanici; miktar, birim fiyat (doviz cinsinden) ve odeme/teslim tarihi girer.
Uygulama, guncel kuru ve Prophet modelinin ilgili tarih icin urettigi tahmin
araligini (yhat_lower / yhat / yhat_upper) kullanarak TRY fiyatini ve kur
riski payini hesaplar.

Bu uygulama forecast.py tarafindan onceden uretilmis forecast_*.csv ve
metrics_*.json dosyalarini okur (Prophet'i her seferinde yeniden egitmek
yavas oldugu icin). Once su iki scripti calistirmis olmak gerekir:

    .venv\\Scripts\\python.exe main.py
    .venv\\Scripts\\python.exe forecast.py

Calistirmak icin:
    .venv\\Scripts\\python.exe -m streamlit run app.py
"""
import json
from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from forecasting import CURRENCY_NAMES, CURRENCY_SERIES, data_path, forecast_path, metrics_path

HISTORY_DISPLAY_DAYS = 180  # grafikte gosterilecek gecmis veri uzunlugu

st.set_page_config(page_title="Doviz Bazli Fiyatlandirma", page_icon="\U0001F4B1")

CURRENCIES = {
    code: {
        "data": data_path(code),
        "forecast": forecast_path(code),
        "metrics": metrics_path(code),
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


st.title("\U0001F4B1 Doviz Bazli Urun Fiyatlandirma")
st.caption(
    "TCMB EVDS'in yayinladigi tum aktif doviz kurlari icin Prophet tahmin "
    "modeline dayali fiyatlandirma ve kur riski araci."
)

col1, col2 = st.columns(2)
with col1:
    currency = st.selectbox(
        "Doviz cinsi",
        list(CURRENCIES.keys()),
        format_func=lambda code: f"{code} - {CURRENCY_NAMES.get(code, code)}",
    )
with col2:
    quantity = st.number_input("Urun miktari (adet)", min_value=1, value=100, step=1)

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
        f"Gerekli veri dosyasi bulunamadi: {e.filename}\n\n"
        f"{currency} icin once terminalde sirasiyla su iki scripti calistirin:\n"
        "1) `python main.py`\n2) `python forecast.py`"
    )
    st.stop()

min_date = forecast_df["ds"].min().date()
max_date = forecast_df["ds"].max().date()
default_target = min(date.today() + timedelta(days=30), max_date)

target_date = st.date_input(
    "Odeme / teslim tarihi",
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
# Bu durumda payi 0'da tabanlamak yerine oldugu gibi negatif gosteriyoruz -
# kullaniciya "modele gore kur su kadar dusebilir" bilgisini de veriyor.
risk_try = high_price_try - current_price_try
risk_pct = (closest["yhat_upper"] - current_rate) / current_rate * 100

st.divider()
st.subheader("Sonuclar")

st.metric(f"Guncel kur ({current_rate_date.date()})", f"{current_rate:.4f} TRY")

m1, m2, m3 = st.columns(3)
m1.metric("Guncel kura gore fiyat", f"{current_price_try:,.2f} TRY")
m2.metric(
    f"Tahmini fiyat ({closest['ds'].date()})", f"{expected_price_try:,.2f} TRY"
)
# st.metric, delta metnindeki ok/renk yonunu ilk karakterin +/- olmasina
# bakarak seciyor. Turkce "%X" bicimini korumak icin isareti basa alip
# yuzde isaretini ondan sonra koyuyoruz (ornek: "-%1.82"), yoksa "%" onek
# oldugundan negatif deger de yesil/yukari ok ile gosteriliyordu.
if risk_try >= 0:
    m3.metric("Kur riski payi (ust sinira gore)", f"+{risk_try:,.2f} TRY", f"+%{risk_pct:.2f}")
else:
    m3.metric("Kur riski payi (ust sinira gore)", f"{risk_try:,.2f} TRY", f"-%{abs(risk_pct):.2f}")

st.write(
    f"**Tahmini fiyat araligi ({closest['ds'].date()}):** "
    f"{low_price_try:,.2f} TRY -- {high_price_try:,.2f} TRY"
)

st.caption(
    f"Model: {metrics['model'].upper()} "
    f"({currency}/TRY, son {metrics['test_size']} is gunu backtest): "
    f"MAE={metrics['mae']:.4f} TRY, RMSE={metrics['rmse']:.4f} TRY, "
    f"MAPE=%{metrics['mape']:.2f}"
)

st.subheader("Gecmis kur ve tahmin araligi")

history_df = load_history(paths["data"])
recent_history = history_df[
    history_df["date"] >= history_df["date"].max() - pd.Timedelta(days=HISTORY_DISPLAY_DAYS)
]

# Egilimin daha net gorunmesi icin y eksenini 0'dan degil, verinin araligindan
# baslatiyoruz (alt.Scale(zero=False)).
y_min = min(recent_history["rate"].min(), forecast_df["yhat_lower"].min())
y_max = max(recent_history["rate"].max(), forecast_df["yhat_upper"].max())
y_scale = alt.Scale(domain=[y_min * 0.98, y_max * 1.02], zero=False)

band = (
    alt.Chart(forecast_df)
    .mark_area(opacity=0.2, color="#ff8c42")
    .encode(
        x=alt.X("ds:T", title="Tarih"),
        y=alt.Y("yhat_lower:Q", title=f"{currency}/TRY", scale=y_scale),
        y2="yhat_upper:Q",
    )
)
forecast_line = (
    alt.Chart(forecast_df)
    .mark_line(color="#ff8c42", strokeDash=[5, 3])
    .encode(x="ds:T", y=alt.Y("yhat:Q", scale=y_scale), tooltip=["ds:T", "yhat:Q"])
)
history_line = (
    alt.Chart(recent_history)
    .mark_line(color="#4c78a8")
    .encode(x="date:T", y=alt.Y("rate:Q", scale=y_scale), tooltip=["date:T", "rate:Q"])
)
target_rule = (
    alt.Chart(pd.DataFrame({"d": [pd.Timestamp(target_date)]}))
    .mark_rule(color="red", strokeDash=[2, 2])
    .encode(x="d:T")
)

chart = (band + history_line + forecast_line + target_rule).properties(height=380).interactive()
st.altair_chart(chart, use_container_width=True)
st.caption(
    "Mavi çizgi: gerçekleşen kur (son "
    f"{HISTORY_DISPLAY_DAYS} gün). Turuncu kesikli çizgi: tahmin (yhat), turuncu "
    "bant: belirsizlik aralığı (yhat_lower–yhat_upper). Kırmızı kesikli çizgi: "
    "seçilen ödeme/teslim tarihi."
)
