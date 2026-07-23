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
from pricing import compute_quote

HISTORY_RANGE_OPTIONS = {
    "Son 180 gün": 180,
    "Son 1 yıl": 365,
    "Tüm geçmiş": None,
}
DEFAULT_HISTORY_RANGE = "Tüm geçmiş"

MAX_COMPARE_CURRENCIES = 4

st.set_page_config(
    page_title="Döviz Bazlı Fiyatlandırma",
    page_icon=":material/currency_exchange:",
)

# dataviz referans paletinin kategorik 1. (mavi) ve 2. (turuncu) slotlari - acik/
# koyu tema icin ayri adimlanmis (bkz. .streamlit/config.toml [theme.light/dark]).
# st.context.theme.type aktif temayi (kullanicinin sistem tercihi veya elle
# sectigi) yansitir, bu yuzden grafik renkleri de ona gore secilir.
if st.context.theme.type == "dark":
    COLOR_HISTORY = "#3987e5"
    COLOR_FORECAST = "#d95926"
else:
    COLOR_HISTORY = "#2a78d6"
    COLOR_FORECAST = "#eb6834"

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

quote = compute_quote(
    current_rate, current_rate_date, forecast_df, metrics["mape"], quantity, unit_price, target_date
)

tab_teklif, tab_karsilastir, tab_grafik, tab_detay = st.tabs(
    ["Teklif", "Karşılaştır", "Grafik", "Model Detayları"]
)

with tab_teklif:
    with st.container(border=True):
        st.caption("Önerilen teklif fiyatı")
        st.markdown(
            f"<div style='font-size:3rem;font-weight:700;line-height:1.15'>"
            f"{quote['recommended_price_try']:,.2f} TRY</div>",
            unsafe_allow_html=True,
        )
        if quote["risk_try"] > 0:
            st.write(
                f"Güncel fiyatın üzerine %{quote['risk_pct']:.2f} kur riski payı eklendi "
                f"(+{quote['risk_try']:,.2f} TRY)."
            )
        else:
            st.write("Model bir düşüş öngörüyor, ek bir güvenlik payına gerek görülmedi.")

        if quote["confidence_high"]:
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
        st.write(f"{quote['current_price_try']:,.2f} TRY")
    with c3:
        st.caption(f"Tahmini aralık ({quote['target_ds'].date()})")
        st.write(f"{quote['low_price_try']:,.2f} – {quote['high_price_try']:,.2f} TRY")

with tab_karsilastir:
    selected_currencies = st.multiselect(
        f"Karşılaştırılacak dövizler (2-{MAX_COMPARE_CURRENCIES})",
        list(CURRENCIES.keys()),
        default=list(CURRENCIES.keys())[:2],
        max_selections=MAX_COMPARE_CURRENCIES,
        format_func=lambda code: f"{code} - {CURRENCY_NAMES.get(code, code)}",
    )

    if len(selected_currencies) < 2:
        st.info("Karşılaştırmak için en az 2 döviz seçin.")
    else:
        compare_data = {}
        missing = None
        for code in selected_currencies:
            cpaths = CURRENCIES[code]
            try:
                c_rate, c_rate_date = load_current_rate(cpaths["data"])
                c_forecast = load_forecast(cpaths["forecast"])
                c_metrics = load_metrics(cpaths["metrics"])
            except FileNotFoundError as e:
                missing = (code, e.filename)
                break
            compare_data[code] = (c_rate, c_rate_date, c_forecast, c_metrics)

        if missing:
            code, filename = missing
            st.error(f"{code} için gerekli veri dosyası bulunamadı: {filename}")
        else:
            # Secilen dovizlerin tahmin ufuklari farkli olabilir (ARIMA ~64 is
            # gunu, Prophet 90 takvim gunu) - ortak tarih secicinin sinirlari
            # bu ufuklarin KESISIMI olmali, aksi halde bir doviz icin gecersiz
            # bir tarih secilebilir.
            shared_min = max(cf.min()["ds"].date() for _, _, cf, _ in compare_data.values())
            shared_max = min(cf.max()["ds"].date() for _, _, cf, _ in compare_data.values())
            shared_default = min(date.today() + timedelta(days=30), shared_max)

            compare_date = st.date_input(
                "Ödeme / teslim tarihi (tüm dövizler için ortak)",
                value=shared_default,
                min_value=shared_min,
                max_value=shared_max,
                key="compare_date",
            )

            st.write("")
            cols = st.columns(len(selected_currencies))
            row_inputs = {}
            for col, code in zip(cols, selected_currencies):
                with col:
                    st.caption(f"**{code}**")
                    row_inputs[code] = (
                        st.number_input("Miktar", min_value=1, value=100, step=1, key=f"cmp_qty_{code}"),
                        st.number_input(
                            f"Birim fiyat ({code})", min_value=0.0, value=10.0, step=0.5, key=f"cmp_price_{code}"
                        ),
                    )

            rows = []
            for code in selected_currencies:
                c_rate, c_rate_date, c_forecast, c_metrics = compare_data[code]
                c_quantity, c_unit_price = row_inputs[code]
                c_quote = compute_quote(
                    c_rate, c_rate_date, c_forecast, c_metrics["mape"], c_quantity, c_unit_price, compare_date
                )
                rows.append(
                    {
                        "Döviz": code,
                        "Güncel fiyat (TRY)": c_quote["current_price_try"],
                        "Önerilen teklif (TRY)": c_quote["recommended_price_try"],
                        "Kur riski payı (TRY)": c_quote["risk_try"],
                        "Güven": "Yüksek" if c_quote["confidence_high"] else "Orta",
                    }
                )

            comparison_df = pd.DataFrame(rows).sort_values("Önerilen teklif (TRY)").reset_index(drop=True)
            cheapest = comparison_df.iloc[0]
            st.success(
                f"En avantajlı: **{cheapest['Döviz']}** — {cheapest['Önerilen teklif (TRY)']:,.2f} TRY "
                f"({compare_date} için)"
            )
            st.dataframe(
                comparison_df.style.format(
                    {
                        "Güncel fiyat (TRY)": "{:,.2f}",
                        "Önerilen teklif (TRY)": "{:,.2f}",
                        "Kur riski payı (TRY)": "{:,.2f}",
                    }
                ),
                hide_index=True,
                use_container_width=True,
            )

            compare_bar = (
                alt.Chart(comparison_df)
                .mark_bar(color=COLOR_HISTORY)
                .encode(
                    x=alt.X("Döviz:N", sort="-y"),
                    y=alt.Y("Önerilen teklif (TRY):Q"),
                    tooltip=["Döviz", alt.Tooltip("Önerilen teklif (TRY):Q", format=",.2f")],
                )
                .properties(height=250)
            )
            st.altair_chart(compare_bar, use_container_width=True)

with tab_grafik:
    with st.container(border=True):
        history_range = st.segmented_control(
            "Geçmiş aralığı",
            list(HISTORY_RANGE_OPTIONS.keys()),
            default=DEFAULT_HISTORY_RANGE,
            label_visibility="collapsed",
        )
        if history_range is None:
            history_range = DEFAULT_HISTORY_RANGE
        history_days = HISTORY_RANGE_OPTIONS[history_range]

        history_df = load_history(paths["data"])
        if history_days is None:
            recent_history = history_df
        else:
            recent_history = history_df[
                history_df["date"] >= history_df["date"].max() - pd.Timedelta(days=history_days)
            ]

        # Eksen olceklendirmesi gercekleşen kur + nokta tahmine (yhat) gore
        # yapilir, yhat_lower/yhat_upper'in en uc degerlerine gore DEGIL. ARIMA
        # secilen dovizlerde (ornegin EUR, GBP, NOK) belirsizlik araligi ufkun
        # sonuna dogru cok genisleyebiliyor (30-90 gunde +/-5 TRY gibi); eksen
        # bu en uc degerlere gore olceklenirse gercek kur cizgisi grafigin kucuk
        # bir kismina sikisip okunmasi zorlasiyor (tutulan nokta ile eksenin
        # gosterdigi deger arasinda gorsel uyumsuzluk). Bant yine de ciziliyor,
        # sadece gorunur alanin disina tasan kismi kirpiliyor (clip=True) - bu,
        # "buradan sonra belirsizlik cok daha buyuk" bilgisini dogru bicimde
        # (abartmadan) tasimaya devam ediyor.
        narrow_min = min(recent_history["rate"].min(), forecast_df["yhat"].min())
        narrow_max = max(recent_history["rate"].max(), forecast_df["yhat"].max())
        padding = max((narrow_max - narrow_min) * 0.15, narrow_max * 0.01)
        # Kur asla negatif olamaz - "Tum gecmis" secildiginde (uzun donem araligi
        # cok genis oldugu icin oransal payin mutlak degeri de buyuyor) alt sinir
        # 0'in altina dusebiliyordu; burada tabanliyoruz.
        y_scale = alt.Scale(domain=[max(narrow_min - padding, 0), narrow_max + padding], zero=False)

        # Her katmana ACIK tooltip tanimlanir. Tanimlanmazsa Vega-Lite otomatik
        # bir tooltip uretiyor ve y ekseninin baslidgini (f"{currency}/TRY")
        # yhat_lower alaninin etiketi sanip oyle gosteriyor - imlec dashed
        # cizgiye (yhat) degil altindaki genis banda denk geldiginde kafa
        # karistirici/yanlis gorunumlu degerler (ornegin "EUR/TRY: 51.99"
        # ama gorsel olarak cizgi 54.1'de) cikmasina yol aciyordu.
        #
        # Bant ve tahmin cizgisi AYNI forecast_tooltip'i kullanir (alt sinir,
        # ortalama/yhat, ust sinir bir arada) - boylece kullanici hangisine
        # tutunursa tutunsun (ince kesikli cizgiye tam denk gelmese bile) ayni
        # eksiksiz bilgiyi gorur. Bu deseni forecast_df'i kullanan her doviz
        # icin ortak app.py kodu urettigi icin ayarlama tum dovizlere otomatik
        # uygulanir, tek tek her doviz icin ayri kod gerekmez.
        forecast_tooltip = [
            alt.Tooltip("ds:T", title="Tarih"),
            alt.Tooltip("yhat_lower:Q", title="Alt sınır", format=",.4f"),
            alt.Tooltip("yhat:Q", title="Ortalama (yhat)", format=",.4f"),
            alt.Tooltip("yhat_upper:Q", title="Üst sınır", format=",.4f"),
        ]
        band = (
            alt.Chart(forecast_df)
            .mark_area(opacity=0.15, color=COLOR_FORECAST, clip=True)
            .encode(
                x=alt.X("ds:T", title="Tarih"),
                y=alt.Y("yhat_lower:Q", title=f"{currency}/TRY", scale=y_scale),
                y2="yhat_upper:Q",
                tooltip=forecast_tooltip,
            )
        )
        forecast_line = (
            alt.Chart(forecast_df)
            .mark_line(color=COLOR_FORECAST, strokeWidth=2, strokeDash=[5, 3], clip=True)
            .encode(
                x="ds:T",
                y=alt.Y("yhat:Q", scale=y_scale),
                tooltip=forecast_tooltip,
            )
        )
        history_line = (
            alt.Chart(recent_history)
            .mark_line(color=COLOR_HISTORY, strokeWidth=2)
            .encode(
                x="date:T",
                y=alt.Y("rate:Q", scale=y_scale),
                tooltip=[
                    alt.Tooltip("date:T", title="Tarih"),
                    alt.Tooltip("rate:Q", title="Gerçekleşen kur", format=",.4f"),
                ],
            )
        )
        target_rule = (
            alt.Chart(pd.DataFrame({"d": [pd.Timestamp(target_date)]}))
            .mark_rule(color=COLOR_FORECAST, strokeDash=[2, 2])
            .encode(x="d:T")
        )

        chart = (band + history_line + forecast_line + target_rule).properties(height=380).interactive()
        st.altair_chart(chart, use_container_width=True)
        st.caption(
            f"Mavi çizgi: gerçekleşen kur ({history_range.lower()}). Turuncu kesikli "
            "çizgi: tahmin (yhat), turuncu bant: belirsizlik aralığı (yhat_lower–"
            "yhat_upper) — okunabilirlik için eksen aralığı gerçekleşen kur ve "
            "tahmine göre ayarlanır, bant görünür alanın dışına taşabilir (belirsizlik "
            "ufka doğru arttıkça normaldir). \"Tüm geçmiş\" seçiliyken uzun vadeli "
            "yükseliş, yakın dönem/tahmin detayını sıkıştırabilir — grafik "
            "yakınlaştırılıp kaydırılabilir (interaktif). Dikey kesikli çizgi: seçilen "
            "ödeme/teslim tarihi."
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
