"""
pricing.compute_quote icin testler. Fonksiyon tamamen saf (disk I/O yok,
Streamlit'e bagli degil) oldugu icin sentetik forecast_df'lerle hizlica
test edilebiliyor.
"""
from datetime import date

import pandas as pd
import pytest

import pricing


def _forecast_df():
    return pd.DataFrame(
        {
            "ds": pd.to_datetime(["2026-08-01", "2026-08-02", "2026-08-03"]),
            "yhat": [50.0, 51.0, 52.0],
            "yhat_lower": [49.0, 49.5, 50.0],
            "yhat_upper": [51.0, 52.5, 54.0],
        }
    )


class TestComputeQuote:
    def test_recommended_price_adds_positive_risk_margin(self):
        quote = pricing.compute_quote(
            current_rate=48.0,
            current_rate_date=date(2026, 7, 23),
            forecast_df=_forecast_df(),
            mape=0.5,
            quantity=100,
            unit_price=10.0,
            target_date=date(2026, 8, 1),
        )
        # current_price = 100*10*48 = 48000; yhat_upper=51 -> high=51000
        # risk_try = 51000-48000 = 3000 (pozitif) -> recommended = 48000+3000
        assert quote["current_price_try"] == pytest.approx(48000.0)
        assert quote["risk_try"] == pytest.approx(3000.0)
        assert quote["recommended_price_try"] == pytest.approx(51000.0)

    def test_recommended_price_stays_at_current_when_risk_negative(self):
        # yhat_upper (51) guncel kurdan (55) dusukse risk negatif olur.
        quote = pricing.compute_quote(
            current_rate=55.0,
            current_rate_date=date(2026, 7, 23),
            forecast_df=_forecast_df(),
            mape=0.5,
            quantity=100,
            unit_price=10.0,
            target_date=date(2026, 8, 1),
        )
        assert quote["risk_try"] < 0
        assert quote["recommended_price_try"] == pytest.approx(quote["current_price_try"])

    def test_confidence_high_below_threshold(self):
        quote = pricing.compute_quote(
            current_rate=48.0,
            current_rate_date=date(2026, 7, 23),
            forecast_df=_forecast_df(),
            mape=0.99,
            quantity=1,
            unit_price=1.0,
            target_date=date(2026, 8, 1),
        )
        assert quote["confidence_high"] is True

    def test_confidence_not_high_at_or_above_threshold(self):
        quote = pricing.compute_quote(
            current_rate=48.0,
            current_rate_date=date(2026, 7, 23),
            forecast_df=_forecast_df(),
            mape=1.0,
            quantity=1,
            unit_price=1.0,
            target_date=date(2026, 8, 1),
        )
        assert quote["confidence_high"] is False

    def test_picks_nearest_forecast_date(self):
        # Hedef tarih (2026-08-04) forecast_df'te yok; en yakini 2026-08-03 olmali.
        quote = pricing.compute_quote(
            current_rate=48.0,
            current_rate_date=date(2026, 7, 23),
            forecast_df=_forecast_df(),
            mape=0.5,
            quantity=1,
            unit_price=1.0,
            target_date=date(2026, 8, 4),
        )
        assert quote["target_ds"] == pd.Timestamp("2026-08-03")

    def test_quantity_and_unit_price_scale_linearly(self):
        base = pricing.compute_quote(
            current_rate=48.0,
            current_rate_date=date(2026, 7, 23),
            forecast_df=_forecast_df(),
            mape=0.5,
            quantity=1,
            unit_price=1.0,
            target_date=date(2026, 8, 1),
        )
        scaled = pricing.compute_quote(
            current_rate=48.0,
            current_rate_date=date(2026, 7, 23),
            forecast_df=_forecast_df(),
            mape=0.5,
            quantity=10,
            unit_price=5.0,
            target_date=date(2026, 8, 1),
        )
        assert scaled["current_price_try"] == pytest.approx(base["current_price_try"] * 50)
        assert scaled["recommended_price_try"] == pytest.approx(base["recommended_price_try"] * 50)
