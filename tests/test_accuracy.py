"""
accuracy.py'nin compute_accuracy fonksiyonu icin testler. forecast_history_path
ve data_path, gercek data/ dosyalarina degil, her testin kendi tmp_path'ine
monkeypatch ile yonlendirilir - boylece testler birbirinden ve gercek proje
verisinden tamamen izole calisir.
"""
import pandas as pd
import pytest

import accuracy


def _write_history(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_actual(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)


class TestComputeAccuracy:
    def test_returns_none_when_history_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(accuracy, "forecast_history_path", lambda code: str(tmp_path / "yok.csv"))

        assert accuracy.compute_accuracy("USD") is None

    def test_returns_none_when_no_target_date_has_happened_yet(self, tmp_path, monkeypatch):
        hist_path = tmp_path / "history.csv"
        _write_history(
            hist_path,
            {
                "generated_on": ["2026-07-23"],
                "ds": ["2026-08-01"],  # henuz gerceklesmemis
                "yhat": [50.0],
                "yhat_lower": [49.0],
                "yhat_upper": [51.0],
            },
        )
        actual_path = tmp_path / "actual.csv"
        _write_actual(actual_path, {"date": ["2026-07-22"], "rate": [47.0]})

        monkeypatch.setattr(accuracy, "forecast_history_path", lambda code: str(hist_path))
        monkeypatch.setattr(accuracy, "data_path", lambda code: str(actual_path))

        assert accuracy.compute_accuracy("USD") is None

    def test_computes_expected_mae_and_horizon_buckets(self, tmp_path, monkeypatch):
        hist_path = tmp_path / "history.csv"
        _write_history(
            hist_path,
            {
                "generated_on": ["2026-07-10", "2026-07-10", "2026-07-10"],
                "ds": ["2026-07-12", "2026-07-15", "2026-07-20"],
                "yhat": [47.0, 47.5, 48.0],
                "yhat_lower": [46.5, 47.0, 47.5],
                "yhat_upper": [47.5, 48.0, 48.5],
            },
        )
        actual_path = tmp_path / "actual.csv"
        _write_actual(
            actual_path,
            {
                "date": ["2026-07-12", "2026-07-15", "2026-07-20"],
                "rate": [47.2, 47.3, 48.4],
            },
        )

        monkeypatch.setattr(accuracy, "forecast_history_path", lambda code: str(hist_path))
        monkeypatch.setattr(accuracy, "data_path", lambda code: str(actual_path))

        result = accuracy.compute_accuracy("USD")

        assert result is not None
        assert result["n_observations"] == 3
        expected_mae = (abs(0.2) + abs(-0.2) + abs(0.4)) / 3
        assert result["overall_mae"] == pytest.approx(expected_mae, abs=1e-9)
        # horizon_days: 2, 5, 10 gun -> ilk ikisi 1-7 kovasina, ucuncusu 8-30 kovasina
        assert result["by_horizon"]["1-7"]["n_observations"] == 2
        assert result["by_horizon"]["8-30"]["n_observations"] == 1
        assert "31-90" not in result["by_horizon"]

    def test_keeps_nearest_horizon_when_same_date_forecast_twice(self, tmp_path, monkeypatch):
        """Ayni hedef tarih icin iki farkli generated_on'dan tahmin varsa,
        en yakin zamanda uretilen (en kucuk ufuklu) tahmin tutulmali - aksi
        halde ayni gercek gozlem birden fazla kez sayilir."""
        hist_path = tmp_path / "history.csv"
        _write_history(
            hist_path,
            {
                "generated_on": ["2026-07-01", "2026-07-14"],
                "ds": ["2026-07-15", "2026-07-15"],
                "yhat": [40.0, 47.0],  # uzak tahmin cok sapmis, yakin tahmin isabetli
                "yhat_lower": [39.0, 46.5],
                "yhat_upper": [41.0, 47.5],
            },
        )
        actual_path = tmp_path / "actual.csv"
        _write_actual(actual_path, {"date": ["2026-07-15"], "rate": [47.1]})

        monkeypatch.setattr(accuracy, "forecast_history_path", lambda code: str(hist_path))
        monkeypatch.setattr(accuracy, "data_path", lambda code: str(actual_path))

        result = accuracy.compute_accuracy("USD")

        assert result["n_observations"] == 1
        assert result["overall_mae"] == pytest.approx(abs(47.1 - 47.0), abs=1e-9)
