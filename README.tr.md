<div align="center">

# ValueBridge

**Süreç keşfinden ölçülebilir, insan onaylı bir kurumsal iş akışına.**

Yapay zekâ destekli satın alma istisna iş akışı — sınırları belirli, üretim disiplinli bir portföy PoC'si.

[![CI](https://github.com/MertArtun/valuebridge-procurement-poc/actions/workflows/ci.yml/badge.svg)](https://github.com/MertArtun/valuebridge-procurement-poc/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-009688)](https://fastapi.tiangolo.com/)
[![License MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Live demo](https://img.shields.io/badge/demo-live-brightgreen)](https://valuebridge.62-238-40-66.sslip.io)

[English](README.md) | **Türkçe**

</div>

## Ne olduğu

Kurgusal EgeMekanik A.Ş. için 220.000 TL tutarındaki satın alma talebi incelenir. Sistem talep tarihinde geçerli politikayı seçer, yalnızca o tarihe kadar tamamlanmış satın alma kayıtlarından kategori medyanını hesaplar, fiyat sapmasını bulur, teklif ve sertifika kontrollerini yürütür ve gerekli finans onayını oluşturur. Açık insan onayından sonra MockDesk üzerinde atomik ve payload-aware idempotency ile ticket açılır; bütün kritik adımlar audit trail'e kaydedilir.

Model katmanı isteğe bağlıdır ve yalnızca anlatım üretir: serbest metni insanın gözden geçireceği bir taslağa çevirir, kilitlenmiş kararı Türkçe anlatır ve yalnızca yönetişimi yapılmış politika bölümlerinden cevap yazar. Anahtar tanımlı değilse sistem aynı kararları verir; sadece bu üç alan boş kalır.

Amaç, belirsiz bir operasyonel süreci açıklanabilir, denetlenebilir ve test edilebilir bir iş akışına dönüştürmenin nasıl göründüğünü tek bir dar senaryoda göstermektir.

## Canlı demo — 60 saniyelik tur

**https://valuebridge.62-238-40-66.sslip.io**

Ortam hız sınırlıdır ve veritabanı her gece 03:00'te (İstanbul) sıfırlanır; hiçbir denemeniz kalıcı olmaz.

1. **Serbest metinle başlayın.** Talep kutusunda *Hazır örnekler* altındaki **Tek teklifli acil alım** çipine tıklayın, ardından **Taslak Çıkar** deyin. Model yalnızca forma bir taslak yazar ve eksik alanları listeler; hiçbir şeyi analiz etmez. Akış ancak siz formu kontrol edip **Talebi Analiz Et** dediğinizde ilerler.
2. **Hero senaryosunu analiz edin.** Atlas Endüstri, 220.000 TL, 1 teklif, 20 gün teslim → politika bölümlerine atıflı `CONDITIONAL_REVIEW` kararı ve finans onaycısı için açılan tek bir onay kaydı.
3. **Onaylayın, çalıştırın — sonra tekrar çalıştırın.** Finans rolüyle onaylayıp aksiyonu çalıştırdığınızda MockDesk yeni bir ticket döner. Aynı onaylı aksiyonu **ikinci** kez çalıştırdığınızda cevap `ALREADY_PROCESSED` olur ve aynı ticket geri gelir; mükerrer kayıt oluşmaz. İzlemeye değer adım budur: idempotency entegrasyon sınırında zorunlu kılınır, kullanıcının çift tıklamamasına güvenilmez.
4. **Geçilemeyen bir kuralı deneyin.** Tedarikçi alanındaki listeden askıya alınmış **Vega Hidrolik** tedarikçisini seçin. Karar `REJECTED` olur, hiç onay açılmaz ve arayüzde "yine de onayla" gibi bir yol bulunmaz.
5. **Eşikleri yoklayın.** Karşılaştırmalar kesin "büyüktür" mantığıyla çalışır: **200.000 TL** finans onayı gerektirmeden geçer, **200.001 TL** gerektirir. **100.000 TL** üzerinde ikinci teklif zorunludur — hero senaryosunun tek teklifle temiz geçememesinin sebebi de budur.
6. **Asistanı kaçırmayı deneyin.** **Gömülü talimat denemesi** çipi, metnin içine modele yönelik gizli bir talimat yerleştirir. Taslağı çıkarın: gömülü talimat uygulanmaz, veri olarak işaretlenir, `injection_rule_id` ile audit trail'e yazılır.
7. **Politika korpusuna iki soru sorun.** **Finans eşiği** çipi PROC-POL-2026 §4.2'ye atıflı bir cevabı `hybrid` retrieval modunda döner. **Korpus dışı soru** çipi ise korpusta bulunmayan bir şeyi sorar ve sistem bunu açıkça söyler — uydurmak yerine cevapsız bırakır.
8. **Kayıtlara bakın.** Metrik ve audit panelleri ayrı sayaçlardan değil, doğrudan audit trail'den türetilir; az önce yaptığınız her şey oradan yeniden kurulabilir.

## Hero sonucu

| Sinyal | Deterministik sonuç |
|---|---:|
| Talep tutarı | 220.000 TL |
| Geçmiş medyan | 184.500 TL |
| Sapma | %19,2 |
| Gerekli teklif | 2 |
| Alınan teklif | 1 |
| ISO 9001 bitiş | 2026-06-30 |
| Talep tarihi | 2026-08-18 |
| Karar | `CONDITIONAL_REVIEW` |
| Politika atıfları | PROC-POL-2026 §4.2, §4.3; SUP-COMP-2026 §3.1 |
| Açılan onay | Bir adet, `finance_approver` için |
| Modelin yukarıdakilere etkisi | Yok |

Uyumluluk durumu aktif olmayan bir tedarikçiden gelen talep diğer çıkışa gider: karar `REJECTED`, atıf `SUP-COMP-2026 §2.1` olur ve hiç onay açılmaz.

## Karar deterministik, model yalnızca anlatır

Hesaplama, politika kuralları, yetkilendirme, onay durumu, retrieval kapsamı ve idempotency hiçbir koşulda model çıktısına bağlı değildir. Model kilitlenmiş bir kararı anlatır, insanın onaylayacağı bir taslak yazar ve yalnızca retrieval'ın zaten yönetişimini yaptığı bölümlerden cevap verir. Testler, model katmanı açıkken ve kapalıyken karar alanlarının bayt bayt aynı kaldığını doğrular.

## Doğrulama

- **211 test** — davranış, güvenlik, eşzamanlılık ve model sınırı testleri
- **9 proje invariant'ı** — `scripts/verify.py`
- **15 donmuş değerlendirme senaryosu** — `scripts/run_evals.py`

Tamamı sağlayıcı anahtarı olmadan koşar; CI hiçbir zaman bir model sağlayıcısına çıkmaz. Bu kontroller sistem davranışını doğrular, müşteri getirisini veya üretim etkisini değil.

## Bilinen sınırlar

- Sentetik saha keşfi ve operasyon verisi
- Üretim kimlik doğrulaması/SSO yerine demo header'ları
- Yönetişimli kurumsal bilgi altyapısı yerine dosya tabanlı politika deposu
- Yönetilen PostgreSQL yerine SQLite
- Tam bir içerik güvenliği sistemi yerine örüntü tabanlı injection tespiti
- Değişmez kurumsal audit altyapısı yerine yerel ve değiştirilebilir audit deposu
- Canlı SkyStudio, Jira veya ERP çalışma alanı yok; ölçülmüş benimsenme veya çevrim süresi sonucu yok

## Bağımsız çalışma notu

Bu depo resmî bir SKYMOD ürünü değildir ve SKYMOD tarafından desteklenmemektedir. SKYMOD ve SkyStudio markaları sahiplerine aittir. EgeMekanik A.Ş., Atlas Endüstri ve tüm operasyonel veriler sentetiktir.

---

Teknik derinlik, mimari ve güvenlik sınırları için [İngilizce README](README.md) ve `docs/` klasörü.
