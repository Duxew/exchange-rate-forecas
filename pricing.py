"""
Tek bir istegin (doviz + miktar + birim fiyat + hedef tarih) teklif fiyati
hesabini yapan, Streamlit'e bagli olmayan saf mantik. app.py hem tekli
Teklif sekmesinde hem coklu Karsilastir sekmesinde ayni compute_quote
fonksiyonunu cagirir - boylece hesaplama iki yerde ayri ayri yazilip
birbirinden sapmiyor, ve Streamlit calistirmadan test edilebiliyor
(bkz. tests/test_pricing.py).
"""

# ONERI_DOKUMANI.md'deki guven tablosuyla birebir ayni esik (%1 alti = yuksek guven).
HIGH_CONFIDENCE_MAPE_THRESHOLD = 1.0


def compute_quote(current_rate, current_rate_date, forecast_df, mape, quantity, unit_price, target_date):
    """forecast_df: forecast.py'nin urettigi ds/yhat/yhat_lower/yhat_upper semali
    DataFrame. target_date: datetime.date. Donen sozluk hem hero fiyat/rozet
    (Teklif sekmesi) hem karsilastirma tablosu (Karsilastir sekmesi) icin
    yeterli alanlari icerir."""
    # Secilen tarih hafta sonuna/tatile denk gelebilir; en yakin tahmini bul.
    day_diff = (forecast_df["ds"].dt.date - target_date).abs()
    closest = forecast_df.loc[day_diff.idxmin()]

    foreign_amount = quantity * unit_price
    current_price_try = foreign_amount * current_rate
    expected_price_try = foreign_amount * closest["yhat"]
    low_price_try = foreign_amount * closest["yhat_lower"]
    high_price_try = foreign_amount * closest["yhat_upper"]

    # Model ust sinirin altinda bir kur da ongorebilir (kur dususu bekleniyor
    # demektir). Ham payi (negatif olabilir) hesaplayip donduruyoruz, ama
    # onerilen teklif fiyatina sadece pozitifse ekliyoruz.
    risk_try = high_price_try - current_price_try
    risk_pct = (closest["yhat_upper"] - current_rate) / current_rate * 100

    # ONERI_DOKUMANI.md'nin onerdigi fiyatlandirma kurali: "guncel kura gore
    # fiyat + kur riski payi". Model dusus ongoruyorsa (risk_try negatif)
    # fiyati asagi cekmek yerine guncel fiyatta birakiyoruz - dokumanin
    # "teklif yine de temkinli verilmeli" notuyla tutarli.
    recommended_price_try = current_price_try + max(risk_try, 0)

    return {
        "target_ds": closest["ds"],
        "current_rate": current_rate,
        "current_rate_date": current_rate_date,
        "current_price_try": current_price_try,
        "expected_price_try": expected_price_try,
        "low_price_try": low_price_try,
        "high_price_try": high_price_try,
        "risk_try": risk_try,
        "risk_pct": risk_pct,
        "recommended_price_try": recommended_price_try,
        "confidence_high": mape < HIGH_CONFIDENCE_MAPE_THRESHOLD,
    }
