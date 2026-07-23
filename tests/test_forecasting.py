"""
forecasting.py'deki hizli/saf fonksiyonlarin testleri. Prophet/ARIMA
egitimi gerektiren fonksiyonlar (train_prophet, evaluate_holdout,
select_best_model, forecast_future*) kasitli olarak burada test
edilmiyor - her biri gercek bir model egitir, ~saniyeler-dakikalar surer
ve cmdstan kurulumu gerektirir, bu da hizli/rutin test calistirmayi
imkansiz hale getirir.
"""
import pandas as pd
import pytest

import forecasting


class TestPathHelpers:
    def test_data_path_lowercases_code(self):
        assert forecasting.data_path("USD") == forecasting.data_path("usd")
        assert forecasting.data_path("USD") == "data/raw/usd_try_data.csv"

    def test_forecast_path_lowercases_code(self):
        assert forecasting.forecast_path("EUR") == "data/forecasts/forecast_eur.csv"

    def test_metrics_path_lowercases_code(self):
        assert forecasting.metrics_path("GBP") == "data/metrics/metrics_gbp.json"

    def test_forecast_history_path_lowercases_code(self):
        assert forecasting.forecast_history_path("RUB") == "data/forecast_history/history_rub.csv"

    def test_accuracy_path_lowercases_code(self):
        assert forecasting.accuracy_path("NOK") == "data/accuracy/accuracy_nok.json"

    def test_model_comparison_path_is_fixed(self):
        assert forecasting.model_comparison_path() == "data/model_comparison.json"


class TestLoadSeries:
    def test_renames_columns_and_parses_dates(self, tmp_path):
        csv_path = tmp_path / "sample.csv"
        csv_path.write_text("date,rate\n2024-01-01,10.5\n2024-01-02,10.7\n")

        df = forecasting.load_series(str(csv_path))

        assert list(df.columns) == ["ds", "y"]
        assert pd.api.types.is_datetime64_any_dtype(df["ds"])
        assert df["y"].tolist() == [10.5, 10.7]


class TestLimitWindow:
    def test_keeps_only_last_window_days(self):
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        df = pd.DataFrame({"ds": dates, "y": range(100)})

        windowed = forecasting._limit_window(df, window_days=10)

        assert windowed["ds"].max() == dates.max()
        assert windowed["ds"].min() == dates.max() - pd.Timedelta(days=10)
        assert len(windowed) == 11

    def test_returns_all_rows_when_window_exceeds_history(self):
        dates = pd.date_range("2024-01-01", periods=5, freq="D")
        df = pd.DataFrame({"ds": dates, "y": range(5)})

        windowed = forecasting._limit_window(df, window_days=730)

        assert len(windowed) == 5

    def test_resets_index(self):
        dates = pd.date_range("2024-01-01", periods=20, freq="D")
        df = pd.DataFrame({"ds": dates, "y": range(20)})

        windowed = forecasting._limit_window(df, window_days=5)

        assert windowed.index.tolist() == list(range(len(windowed)))
