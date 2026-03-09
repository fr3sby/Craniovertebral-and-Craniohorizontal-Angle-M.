# Craniovertebral and Craniohorizontal Angle Measurement Tool

Bu proje, fotoğraflar üzerinden aşağıdaki açıların manuel landmark işaretleme ile ölçülmesini sağlar:

- **Craniovertebral (CV) açısı**: C7 → Tragus doğrusu ile horizontal eksen arasındaki açı.
- **Cranial Rotation (CR) açısı**: Tragus noktasında, C7-Tragus doğrusu ile Tragus-Cantus doğrusu arasındaki açı.
- **Craniohorizontal (CH) açısı**: Tragus → Cantus doğrusu ile horizontal eksen arasındaki açı.

## Özellikler

- Klasör seçerek tüm görselleri solda listeleme
- Seçili görseli ortada büyük ve sığdırılmış gösterme
- C7, Tragus, Cantus noktalarını tıklama ile belirleme
- Noktaları sürükleyip konumu düzeltme
- Açıyı gerçek zamanlı hesaplama ve çizgilerle görselleştirme
- Sonuçları sağ panelde metin olarak gösterme
- Ölçümleri seçili klasörde SQLite veritabanına otomatik kaydetme (`angle_measurements.db`)
- Tüm sonuçları Excel'e aktarma (`angle_measurements.xlsx`)

## Kurulum

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install pillow pandas openpyxl
```

## Çalıştırma

```bash
python cranio_angle_app.py
```

## Kayıt Formatı (Excel)

- Görsel adı
- Görsel tarihi (EXIF'ten, yoksa dosya oluşturma/değiştirme zamanı)
- CV açısı
- CR açısı
- CH açısı
