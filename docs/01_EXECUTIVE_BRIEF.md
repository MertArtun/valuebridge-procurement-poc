# Executive Brief

## Ne yapıyoruz?

ValueBridge, kurgusal bir üretim şirketinin satın alma istisna sürecini discovery'den kontrollü kurumsal aksiyona kadar modelleyen bir Forward-Deployed Solution Engineering vaka çalışmasıdır. Kahraman senaryoda Atlas Endüstri'den gelen 220.000 TL'lik yedek parça teklifi güncel satın alma politikası, geçmiş satın alma kayıtları ve tedarikçi uyum bilgileri üzerinden incelenir.

Sistem geçmiş kategori medyanını 184.500 TL olarak hesaplar; teklifin bunun %19,2 üzerinde olduğunu gösterir; iki teklif zorunluluğunun karşılanmadığını, ISO 9001 belgesinin talep tarihinde geçerli olmadığını ve finans onayı gerektiğini belirler. Sonuç doğal dille açıklanır, ancak karar normal kodla çalışan deterministik kurallardan gelir. MockDesk ticket'ı yalnızca açık insan onayından sonra oluşturulur ve aynı idempotency key ile ikinci kayıt açılamaz.

## Neden bunu yapıyoruz?

Solution Engineer/FDE rolünde ayırt edici yetkinlik model çağrısı yapmak değil; müşterinin gerçek iş akışını anlamak, belirsizlikleri gereksinimlere dönüştürmek, doğru insan–AI sınırlarını kurmak, kurumsal entegrasyonu güvenli şekilde yürütmek ve sonucu ölçülebilir hâle getirmektir.

ValueBridge şu iddiayı somutlaştırır:

> Müşteri sürecini haritalandırabilir, kritik dikey dilimi hızla geliştirebilir, güvenlik ve reliability kontrollerini ekleyebilir, pilot ve handoff yolunu açıklayabilirim.

## Neden procurement?

Satın alma süreci FDE becerilerini göstermek için güçlüdür çünkü aynı anda:

- Birden fazla aktör içerir.
- Güncel politika ve belge sürümü gerektirir.
- Sayısal analiz gerektirir.
- İstisna ve onay kuralları içerir.
- Haricî sisteme write action üretir.
- Hata ve duplicate riskleri taşır.
- Operasyonel etki metrikleriyle ölçülebilir.

SKYMOD'un kamuya açık Chef Seasons vaka anlatımında Supply Chain Assistant'ın tedarikçi ilişkileri ve satın alma süreçleriyle ilişkilendirilmesi, bu dikeyin platformun müşteri dünyasına yabancı olmadığını gösterir. Bu proje söz konusu vakanın kopyası değildir; procurement exception, human approval ve reliability boyutlarını bağımsız sentetik bir senaryoda işler.

## Projenin sınırı

Bu paket production deployment değildir. Gerçek müşteri, gerçek Jira, gerçek ERP, canlı SkyStudio workspace veya doğrulanmış iş sonucu içermez. Hedef; dar, çalışan, test edilebilir ve dürüst bir portföy dikey dilimidir.

## Başarı tanımı

Teknik başarı:

- Doğru politika sürümünün seçilmesi
- Doğru matematik ve tarih kontrolleri
- Onaysız write action sayısının sıfır olması
- Duplicate ticket sayısının sıfır olması
- Yetkisiz belge erişiminin engellenmesi
- Zararlı belge talimatlarının kontrol akışını değiştirememesi
- Kritik olayların audit trail'de bulunması

Demo başarısı:

- 90 saniyede anlaşılabilen bir demo
- Tek komutla çalıştırılabilen repository
- İlan sorumluluklarıyla açık traceability
- Mimari, güvenlik, ölçüm ve handoff disiplininin görünmesi
