# PRD — Algoritmik Hisse Sinyal ve Açıklama Platformu (MVP)

## 1) Orijinal Problem Statement (Özet)
- BIST + ABD hisselerini tarayan, teknik + temel analiz yapan, formasyonları matematiksel tespit eden ve AL/SAT/TUT sinyali üreten dashboard.
- Zorunlu teknik kurallar: Double Top/Bottom, OBO/Ters OBO, EMA20/SMA50/SMA200, Golden/Death Cross, RSI/MACD ve negatif uyumsuzluk.
- Karar motoru: 0–100 Bullish Score ve eşiklere göre aksiyon sınıflaması.
- Risk yönetimi: ATR tabanlı Stop-Loss/Take-Profit.
- XAI: Hisse bazında LLM ile “Neden?” raporu.
- UI: Karanlık tema, solda sinyal akışı, sağda TradingView, tıklamada sağ panel AI raporu.

## 2) Kullanıcı Seçimleri
- LLM: Gemini 3 Flash (Emergent universal key)
- Veri kaynağı: Pluggable mimari, MVP’de Yahoo Finance (US + BIST .IS)
- Evren/Zaman: Top 100 US + Top 100 BIST, günlük periyot
- Yenileme: 5 dakikada bir
- Öncelik: Görsel formasyon tespitinin güçlü gösterimi

## 3) Mimari Kararları
- Backend: FastAPI + MongoDB (Motor), tek servis içinde tarama/sinyal üretim/explain endpoint’leri.
- Veri pipeline: yfinance OHLCV + temel metrikler; TA-Lib ile EMA/SMA/RSI/MACD/ATR; scipy argrelextrema ile swing noktaları.
- Pattern engine:
  - Double Top/Bottom: son 60 periyotta %2 tolerans + neckline kırılımı
  - OBO/Ters OBO: omuz-baş-omuz, başta %3 fark + hacim doğrulaması
- Scoring engine: Teknik (30) + MA (20) + Hacim (20) + Temel (30), uyumsuzlukta ceza.
- Risk engine: ATR(14) tabanlı dinamik SL/TP (1:2).
- LLM açıklama: Gemini 3 Flash (emergentintegrations) + fallback lokal özet.
- Frontend: React dashboard (dark, yoğun veri hiyerarşisi), sinyal listesi + pattern grafiği + TradingView + sağdan AI detail sheet.

## 4) Uygulanan Kapsam (Implemented)
- `/api` kök + config + scanner state + manuel run endpoint’leri.
- 200 sembollük tarama döngüsü (100 US + 100 BIST), 5 dk scheduler.
- MongoDB’de sinyal cache ve fundamental cache (24h) yönetimi.
- Sinyal endpoint’leri:
  - `GET /api/signals`
  - `GET /api/signals/{symbol}`
  - `POST /api/signals/{symbol}/explain`
- Formasyon, indikatör, skor matrisi, ATR risk çıktılarının response’a dahil edilmesi.
- Frontend dashboard:
  - Üstte filtre/arama/tarama kontrolleri
  - Solda “Sinyal Akışı”
  - Ortada görsel pattern chart + marker’lar + skor kırılımı
  - Sağda TradingView widget + risk kartı + scanner health
  - Sinyal tıklanınca sağdan AI rapor paneli
- data-testid kapsamı: kritik etkileşim ve kullanıcıya görünen ana metrik öğeleri.
- Test:
  - Self-test: curl + Playwright screenshot
  - Testing agent: iteration_1 raporu, backend API 6/6 pass, frontend ana akış doğrulandı.

## 5) Kalan Backlog

### P0 (Yüksek Öncelik)
- TradingView sembol çözümlemesi için borsa/exchange fallback stratejisi (bazı sembollerde popup engelleme).
- Scanner performans telemetrisi (sembol bazlı hata oranı, retry/backoff).
- API rate limit/timeout sertleştirme (yfinance geçici hatalarında daha dayanıklı akış).

### P1 (Orta Öncelik)
- Backend modüler refactor (scanner/services/patterns/routes dosya ayrımı).
- Pattern görselleştirmesinde neckline/omuz seviyeleri için ek overlay çizimleri.
- Kullanıcı watchlist modu (özel sembol listesi) + kalıcı tercih kaydı.

### P2 (Düşük Öncelik)
- Ek temel veri sağlayıcısı adaptörü (Alpha Vantage plug-in).
- Backtest görünümü ve sinyal başarı istatistikleri.
- Çoklu timeframe (1h/4h/günlük) karşılaştırmalı panel.

## 6) Sonraki Görevler (Next Tasks)
1. TradingView sembol fallback haritasını iyileştir ve UI’da “symbol unavailable” durumunu zarif yönet.
2. Scanner için retry + exponential backoff + hata metrik endpoint’i ekle.
3. Pattern chart’ta neckline ve kırılım anı için görsel annotation katmanı ekle.
4. Backend kodunu modüllere ayırıp bakım maliyetini düşür.

## 7) Son Güncelleme (Hisse Tarayıcı Onarım + Genişletme)
- Rebranding tamamlandı: başlık **Hisse Tarayıcı** ve yeni profesyonel alt açıklama metni uygulandı.
- Kritik senkronizasyon düzeltmesi: `POST /api/signals/analyze/{symbol}` ve `POST /api/signals/{symbol}/reanalyze` artık canlı veriyi zorlayarak (force live fundamentals) aynı `build_signal` hattıyla hesap yapıyor; listede aksiyon tutarlılığı güçlendirildi.
- Hedef fiyat yön güvenliği: görselde kullanılan hedef fiyat artık aksiyon yönüyle matematiksel olarak zorunlu uyumlu (AL/GÜÇLÜ AL için yukarı, SAT/GÜÇLÜ SAT için aşağı).
- Yön çelişkisi hotfix: bullish aksiyonda bearish formasyon görseli seçilmesini engelleyen direction-aware pattern seçimi eklendi; uyumsuzsa görsel üretilmiyor/temizleniyor.
- UI genişletmeleri:
  - Sinyal akışı üstüne **Liste içi filtrele/ara** kutusu
  - Formasyon görselinde **Görseli Büyüt** (fullscreen modal)
  - Formasyon görselinde **Görseli Tekrar Oluştur** butonu
  - AI panelinde sekmeli yapı: **Özet** + **Detaylı Bak**
- Derin analiz alanları:
  - Teknik: Bollinger, Stokastik, ADX, Ichimoku
  - Temel: ROE, Borç/Özsermaye, Net Kar Marjı, Temettü Verimi
- Hacim modülü:
  - Kırılım hacmi > 20g ortalama *1.2 ise skor bonusu + “Hacim Onaylı Kırılım” notu
  - AI raporuna **Hacim Durumu** başlığı eklendi.

