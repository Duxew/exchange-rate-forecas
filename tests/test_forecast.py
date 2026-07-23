"""
forecast.py'nin append_forecast_history fonksiyonu icin testler. Ozellikle
son test, gecmiste bulunup duzeltilen gercek bir bug'in regresyon testidir:
history dosyasi zaten varken parse_dates olmadan okunursa, yeni Timestamp
satirlariyla concat sonucu tarih kolonlari object dtype'a dusup karisik
formatta (bazen "YYYY-MM-DD", bazen "YYYY-MM-DD HH:MM:SS") yaziliyordu; bu
da sonraki okumada parse_dates'in kolonu hic tarihe cevirememesine ve
accuracy.py'nin merge'inin sessizce bosa cikmasina yol aciyordu.
"""
from datetime import date

import pandas as pd
import pytest

import forecast


class _FakeDate(date):
    """date.today()'i testte kontrol edilebilir kilmak icin."""

    _today = date(2026, 7, 23)

    @classmethod
    def today(cls):
        return cls._today


def _future_forecast(ds_list, yhat_list):
    return pd.DataFrame(
        {
            "ds": pd.to_datetime(ds_list),
            "yhat": yhat_list,
            "yhat_lower": [v - 0.5 for v in yhat_list],
            "yhat_upper": [v + 0.5 for v in yhat_list],
        }
    )


class TestAppendForecastHistory:
    def test_creates_new_file_with_datetime_columns(self, tmp_path, monkeypatch):
        hist_path = tmp_path / "history.csv"
        monkeypatch.setattr(forecast, "forecast_history_path", lambda code: str(hist_path))
        monkeypatch.setattr(forecast, "date", _FakeDate)
        _FakeDate._today = date(2026, 7, 23)

        future = _future_forecast(["2026-08-01", "2026-08-02"], [48.0, 48.1])
        result_path = forecast.append_forecast_history("USD", future)

        assert result_path == str(hist_path)
        saved = pd.read_csv(hist_path, parse_dates=["generated_on", "ds"])
        assert len(saved) == 2
        assert (saved["generated_on"] == pd.Timestamp(2026, 7, 23)).all()

    def test_running_twice_same_day_does_not_duplicate(self, tmp_path, monkeypatch):
        hist_path = tmp_path / "history.csv"
        monkeypatch.setattr(forecast, "forecast_history_path", lambda code: str(hist_path))
        monkeypatch.setattr(forecast, "date", _FakeDate)
        _FakeDate._today = date(2026, 7, 23)

        future = _future_forecast(["2026-08-01"], [48.0])
        forecast.append_forecast_history("USD", future)
        forecast.append_forecast_history("USD", future)

        saved = pd.read_csv(hist_path, parse_dates=["generated_on", "ds"])
        assert len(saved) == 1

    def test_dtypes_stay_consistent_across_multiple_days(self, tmp_path, monkeypatch):
        hist_path = tmp_path / "history.csv"
        monkeypatch.setattr(forecast, "forecast_history_path", lambda code: str(hist_path))
        monkeypatch.setattr(forecast, "date", _FakeDate)

        _FakeDate._today = date(2026, 7, 23)
        forecast.append_forecast_history("USD", _future_forecast(["2026-08-01"], [48.0]))

        _FakeDate._today = date(2026, 7, 24)
        forecast.append_forecast_history(
            "USD", _future_forecast(["2026-08-01", "2026-08-02"], [48.05, 48.1])
        )

        saved = pd.read_csv(hist_path, parse_dates=["generated_on", "ds"])

        # Regresyon: her iki kolon da gercek datetime64 olmali, object/string degil.
        assert pd.api.types.is_datetime64_any_dtype(saved["generated_on"])
        assert pd.api.types.is_datetime64_any_dtype(saved["ds"])
        # Farkli generated_on'lar oldugu icin dedup devreye girmez: 1 + 2 = 3 satir.
        assert len(saved) == 3
