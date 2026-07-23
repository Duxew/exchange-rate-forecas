# Döviz Bazlı Fiyatlandırma Aracı

TCMB EVDS API'sinden çekilen güncel kur verileriyle, aktif olarak yayınlanan 20 döviz cinsi için TRY tahmini üreten ve bunu bir ürün/hizmet fiyatlandırma aracına dönüştüren uçtan uca bir sistem. Prophet ve ARIMA modelleri her döviz için ayrı ayrı yarıştırılır, hangisi daha isabetliyse (30 günlük backtest MAPE'ye göre) o seçilir. Sonuçlar bir Streamlit arayüzünde, güncel kur / tahmini kur / önerilen kur riski payı olarak gösterilir.

CNG400 staj projesi kapsamında geliştirilmiştir.

## Özellikler

- **20 döviz, otomatik model seçimi:** Her döviz için Prophet (3 farklı `changepoint_range`) ve ARIMA ayrı ayrı backtest edilir, en düşük hata payına sahip olan üretimde kullanılır.
- **Fiyatlandırma arayüzü (`app.py`):** Miktar, birim fiyat ve ödeme/teslim tarihi girilir; güncel kura göre fiyat, tahmini fiyat aralığı ve önerilen "kur riski payı" gösterilir.
- **Doğruluk geçmişi:** Geçmişte üretilen tahminler, hedefledikleri tarih gerçekleştikçe gerçek kurla otomatik karşılaştırılır; model gerçekten ne kadar isabetli çıkmış, ufka göre (1-7 / 8-30 / 31-90 gün) arayüzde görülebilir.
- **Günlük otomatik yenileme:** GitHub Actions, her gün veri çekme → model eğitimi → doğruluk hesaplamasını kendi kendine çalıştırıp sonucu repoya commit'ler (bkz. [Otomatik yenileme](#otomatik-yenileme-github-actions)).

## Kurulum

```bash
git clone <bu repo>
cd exchangeRateForecast
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt      # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # Linux/Mac
```

TCMB EVDS'ten ücretsiz bir API anahtarı alın ([evds2.tcmb.gov.tr](https://evds2.tcmb.gov.tr)) ve repo kökünde bir `.env` dosyası oluşturun:

```
TCMB_API_KEY=your_key_here
```

## Kullanım

```bash
# 1) Tüm dövizler için güncel veriyi çek
.venv\Scripts\python.exe main.py

# 2) Modelleri eğit, backtest et, tahmin üret (1'den sonra çalıştırılmalı)
.venv\Scripts\python.exe forecast.py

# 3) Geçmiş tahminlerin gerçekleşen doğruluğunu hesapla (2'den sonra çalıştırılmalı)
.venv\Scripts\python.exe accuracy.py

# 4) Fiyatlandırma arayüzünü başlat
.venv\Scripts\python.exe -m streamlit run app.py
```

Opsiyonel: `compare_models.py`, Prophet ve ARIMA'yı 7/30/90 günlük ufuklarda karşılaştıran daha derin bir analiz raporu üretir (şu an sadece USD/EUR için ayrıntılı çalıştırılmıştır, tüm dövizlerde yavaştır).

## Nasıl çalışır

```
main.py ──▶ data/raw/<kod>_try_data.csv
                │
                ▼
forecast.py ──▶ data/forecasts/forecast_<kod>.csv   (güncel tahmin)
            ├──▶ data/metrics/metrics_<kod>.json     (backtest sonucu, seçilen model)
            └──▶ data/forecast_history/history_<kod>.csv  (biriken tahmin geçmişi)
                │
                ▼
accuracy.py ──▶ data/accuracy/accuracy_<kod>.json    (gerçekleşen doğruluk)
                │
                ▼
             app.py (Streamlit arayüzü, yukarıdaki dosyaları okur)
```

`app.py` hiçbir zaman kendi modelini eğitmez — sadece `forecast.py`/`accuracy.py`'nin ürettiği dosyaları okur. Bu yüzden veri yenilendiğinde (`main.py`) mutlaka `forecast.py` ve `accuracy.py` de yeniden çalıştırılmalı, yoksa arayüz eski sonuçları göstermeye devam eder.

Ham veri (`data/raw/`) API'den her an yeniden çekilebildiği için repoda tutulmaz; üretilen tahmin/metrik/doğruluk dosyaları ise küçük olduğu ve otomasyonun sonucunu görünür kıldığı için repoda track edilir.

## Otomatik yenileme (GitHub Actions)

`.github/workflows/refresh.yml`, yukarıdaki `main.py → forecast.py → accuracy.py` zincirini her gün otomatik çalıştırır ve sonucu `github-actions[bot]` olarak repoya commit'ler. Kendi fork'unuzda/kopyanızda çalıştırmak isterseniz repo ayarlarına (Settings → Secrets and variables → Actions) bir `TCMB_API_KEY` secret'i eklemeniz yeterli; Actions sekmesinden "Run workflow" ile elle de tetiklenebilir.

## Proje yapısı

```
main.py             veri çekme (TCMB EVDS)
forecasting.py       ortak model eğitim/tahmin fonksiyonları, döviz listesi
forecast.py          model seçimi + tahmin üretimi + geçmiş biriktirme
accuracy.py           geçmiş tahminlerin gerçekleşen doğruluğunu ölçer
compare_models.py     Prophet vs ARIMA derin karşılaştırma (analiz amaçlı)
app.py                Streamlit fiyatlandırma arayüzü
data/                üretilen veri/tahmin/metrik/doğruluk dosyaları
ONERI_DOKUMANI.md     şirket sürecine entegrasyon için öneri dokümanı
```

## Sınırlamalar

Bu bir yatırım/finansal tavsiye aracı değildir; model geçmiş fiyat hareketlerinden istatistiksel bir tahmin üretir ve ani ekonomik/politik olayları öngöremez. Ayrıntılı kullanım senaryosu ve riskler için `ONERI_DOKUMANI.md`'ye bakın.
