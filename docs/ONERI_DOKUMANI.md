# Döviz Bazlı Fiyatlandırma Aracının Şirket Sürecine Entegrasyonu — Öneri Dokümanı

**Proje:** CNG400 Staj Projesi — USD/TRY ve diğer döviz kurları tahmin modülü
**Kapsam:** Bu doküman, geliştirilen tahmin modelinin ve Streamlit fiyatlandırma arayüzünün şirketin mevcut fiyatlandırma sürecine nasıl entegre edilebileceğine dair somut bir öneri sunar.

---

## 1. Özet

Elimizde şu an çalışan bir sistem var:

- TCMB EVDS'ten günlük olarak çekilen, 20 döviz cinsinin TRY karşılığındaki geçmiş kur verisi
- Her döviz için otomatik olarak Prophet veya ARIMA modelinden (hangisi o dövizde daha isabetliyse) seçilmiş bir tahmin modeli
- Kullanıcının miktar, birim fiyat ve ödeme/teslim tarihi girerek güncel kura göre fiyatı, tahmini kur aralığına göre fiyat aralığını ve bir "kur riski payı" gördüğü bir Streamlit arayüzü (`app.py`)

Bu doküman, bunun bir demo olmaktan çıkıp şirketin gerçek teklif/fiyatlandırma sürecinde kullanılabilir hale gelmesi için gereken adımları özetliyor.

---

## 2. Önerilen Kullanım Senaryosu

**Kimler kullanacak:** Yurt dışından ürün/hizmet alımı veya satımı yapan, teklifini döviz cinsinden veren satış/satın alma ekibi.

**Ne zaman kullanılacak:** Bir müşteriye veya tedarikçiye döviz cinsinden fiyat teklifi hazırlanırken, özellikle **ödeme tarihi teklif tarihinden ileride** olduğunda (ör. 30-90 gün vadeli ödemeler).

**Adım adım:**

1. Satış temsilcisi `app.py` arayüzünü açar, işlemin döviz cinsini seçer.
2. Ürün miktarını ve birim fiyatını (döviz cinsinden) girer.
3. Beklenen ödeme/teslim tarihini girer.
4. Arayüz üç rakam gösterir:
   - **Güncel kura göre fiyat** — bugün ödeme alınsa/verilse ne olurdu
   - **Tahmini fiyat** — modelin o tarih için öngördüğü kura göre
   - **Kur riski payı** — modelin öngördüğü üst sınıra göre, fiyata eklenmesi önerilen ek tutar (model bir düşüş öngörüyorsa bu değer negatif de gösterilir — o durumda ek bir güvenlik payına gerek olmadığı anlamına gelir, ama teklif yine de temkinli verilmeli, bkz. Bölüm 5)

**Fiyatlandırma kuralı önerisi:** Teklif fiyatı, "güncel kura göre fiyat" yerine **"güncel kura göre fiyat + kur riski payı"** olarak verilmelidir. Bu, ödeme tarihine kadar kurun aleyhe hareket etmesi ihtimaline karşı otomatik bir tampon oluşturur ve şirketi kur riskinden kısmen korur.

*Örnek:* 100 adet, birim fiyat 10 USD, ödeme tarihi 30 gün sonra. Güncel kura göre fiyat 47.113 TRY, model üst sınıra göre kur riski payı +705 TRY (%1.5) gösteriyorsa, teklif 47.113 TRY yerine ~47.818 TRY üzerinden verilmelidir.

---

## 3. Operasyonel Gereksinimler

Sistemin güncel kalabilmesi için üç script'in düzenli olarak, bu sırayla çalıştırılması gerekiyor:

```
1) main.py       -> TCMB EVDS'ten en güncel veriyi çeker (tüm 20 döviz, ~1-2 dakika)
2) forecast.py   -> Modelleri yeniden eğitir, tahminleri günceller (~5 dakika)
3) app.py         -> (Streamlit sunucusu zaten açıksa yeniden başlatılmalı — önbellek
                      dosya yolu bazlı çalıştığı için otomatik güncellenmiyor)
```

**Önerilen sıklık:** Günlük, iş günü sabahları (TCMB kurları her iş günü güncellendiği için). Bu, Windows Görev Zamanlayıcısı (Task Scheduler) veya bir sunucuda basit bir cron/zamanlanmış görevle otomatikleştirilebilir — şu an bu otomasyon **kurulu değil**, manuel çalıştırma gerekiyor.

**Sorumluluk:** Verinin güncelliğinden ve script'lerin çalıştırılmasından sorumlu bir kişi/ekip belirlenmeli. Veri güncellenmeden arayüz kullanılırsa, "güncel kur" aslında birkaç gün eskimiş olabilir.

**Ortam:** Sistem şu an tek bir geliştirme makinesinde (`.venv` sanal ortamı) çalışıyor. Şirket içi kullanım için bu, paylaşılan bir sunucuya veya (daha sağlam bir çözüm olarak) küçük bir dahili web sunucusuna taşınmalı ki birden fazla kişi aynı anda erişebilsin.

---

## 4. Model Güvenilirliği — Şeffaf Bir Tablo

Fiyatlandırma kararlarında kullanılacaksa, ekibin hangi dövizlerde modele ne kadar güvenebileceğini bilmesi gerekir. 30 günlük backtest'e göre (MAPE = ortalama mutlak yüzde hata):

| Güven seviyesi | Dövizler | MAPE aralığı |
|---|---|---|
| Yüksek (%1 altı) | USD, EUR, GBP, CHF, AUD, CAD, DKK, SEK, JPY, CNY, AED, SAR, QAR, KWD, AZN, PKR, RON | %0.16 – %0.93 |
| Orta-düşük (%1 üstü) | KRW, NOK, RUB | %1.43 – %2.78 |

KRW, NOK ve RUB için hata payının yüksek olması bir model hatası değil — bu kurların TRY karşısında günlük hareketi diğerlerinden doğal olarak daha oynak (bkz. `CLAUDE.md`, kapsamlı pencere/model denemesine rağmen bu üçü %1'in altına inmiyor). **Bu üç döviz için teklif verirken ek bir manuel güvenlik payı (ör. modelin önerdiği kur riski payının üzerine ekstra %1-2) düşünülmeli**, ya da mümkünse bu dövizlerdeki vadeli işlemler için forward/hedge gibi geleneksel araçlarla desteklenmeli — model tek başına yeterli güvenceyi vermiyor.

Ayrıca: KZT (Kazakistan Tengesi) sisteme dahil edilmedi çünkü TCMB bu kur için yalnızca ~8 aylık veri yayınlıyor; güvenilir bir model için yetersiz. Şirket bu dövizde işlem yapıyorsa, veri biriktikçe (muhtemelen 2026 sonu/2027 başı) yeniden değerlendirilebilir. XDR (Özel Çekme Hakkı / IMF SDR) de listeden çıkarıldı — TCMB tarafından yayınlanıyor olsa da gerçek bir döviz değil, şirketin ürün/hizmet fiyatlandırmasında kullanım alanı yok.

---

## 5. Sınırlamalar ve Riskler (Şeffaflık İçin Önemli)

- **Bu bir yatırım/finansal tavsiye aracı değildir.** Model geçmiş fiyat hareketlerinden istatistiksel bir tahmin üretir; ani ekonomik/politik olaylar (faiz kararı, seçim, jeopolitik kriz) modelin öngöremeyeceği hareketlere yol açabilir. 2021 Aralık TRY krizi gibi bir olay tekrar yaşanırsa, model bunu önceden bilemez.
- **Tahmin aralığı bir garanti değil, istatistiksel bir bant.** "Kur riski payı" olarak gösterilen üst sınır, kurun kesinlikle o seviyeyi aşmayacağı anlamına gelmez — sadece modelin geçmiş performansına göre makul bir üst tahmindir.
- **Model günlük veri gerektirir.** Veri güncellenmezse (bkz. Bölüm 3) tahminler eskir ve güvenilirliği düşer.
- **90 günden uzun vadeli işlemler için şu an destek yok** — arayüz en fazla 90 gün ileriye tahmin üretiyor.

---

## 6. Gelecek Geliştirme Önerileri (Öncelik Sırasına Göre)

1. **Otomatik veri güncelleme** (main.py + forecast.py'nin zamanlanmış görev olarak çalıştırılması) — operasyonel kullanım için ön koşul, henüz yapılmadı.
2. **Senaryo karşılaştırma özelliği** — aynı anda birden fazla döviz/tarih kombinasyonunu karşılaştırma (ör. "3 ay sonra USD ile mi EUR ile mi ödeme almak daha avantajlı").
3. **Geçmiş teklif doğruluğu takibi** — verilen tekliflerin gerçekleşen kur karşısında ne kadar isabetli çıktığının kaydedilip modelin gerçek dünya performansının izlenmesi.
4. **NOK/KRW/RUB için GARCH tipi oynaklık modeli** — bu üç dövizde nokta tahmin yerine oynaklık tahminine odaklanmak daha gerçekçi bir risk payı üretebilir.
5. **Paylaşılan sunucuya taşıma** — tek makine yerine ekip içi erişilebilir bir ortam.

---

*Bu doküman, staj kapsamında geliştirilen `usd_try_data.csv` → `forecasting.py` → `forecast.py` → `app.py` pipeline'ının teknik detayları için proje köküdeki `CLAUDE.md` dosyasına bakılabilir.*
