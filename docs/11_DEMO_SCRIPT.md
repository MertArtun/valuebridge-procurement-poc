# Demo Script

Two storyboards over the same running system: a 90-second executive walkthrough of the happy path, and a five-minute technical tour of the paths that prove the boundaries.

Both assume ValueBridge on `:8000` and MockDesk on `:8001`. The 90-second version needs `VALUEBRIDGE_LLM_API_KEY` set so the intake assistant and the narrative appear; the technical tour runs either way.

## A. 90-second executive demo

### 0–8 s — The process, not the chatbot

Show the as-is chain:

```text
Email → PDF policy → Excel → Finance email → Jira/ERP
```

> Bu projeye chatbot yazarak değil, kurgusal müşterinin satın alma istisna sürecini haritalandırarak başladım.

### 8–20 s — Free text into a reviewable draft

Paste into the intake box:

```text
Atlas Endüstri'den 220 bin TL'lik yedek parça alacağız, tek teklif var,
teslim 21 gün. PR-2026-0042.
```

Press **Taslak Çıkar**. The form fills in; the badge reads `ANALİZE HAZIR`.

> Serbest metni yapılandırılmış talebe asistan çeviriyor. Ama analizi o başlatmıyor: taslağı insan onaylıyor.

### 20–45 s — The deterministic decision

Press **Talebi Analiz Et**. Point at, in order:

- 220.000 TL request against a 184.500 TL median
- 19,2% variance
- One quote where the policy requires two
- ISO 9001 expired on the request date
- `CONDITIONAL_REVIEW` with citations `PROC-POL-2026 §4.2, §4.3` and `SUP-COMP-2026 §3.1`

> Bu sayıların hiçbirini model üretmiyor. Model kilitlenmiş kararı anlatıyor, kararı değiştiremiyor.

### 45–55 s — The narrative, in its place

Show the `Yapay Zekâ Anlatımı` panel next to the decision.

> Anlatımı kapatırsam karar alanları bayt bayt aynı kalıyor. Anlatım onay parmak izine de girmiyor.

### 55–70 s — Human approval, then the write

Show the action preview, press **İnsan Onayını Ver** as the finance user, then **MockDesk Kaydını Oluştur**. MockDesk returns `MD-1001 OPEN`.

> Hiçbir write action açık insan onayı olmadan çalışmıyor. Onay kaydı sistemde tutuluyor, arayüzde değil.

### 70–80 s — Press execute again

The same ticket comes back as `ALREADY_PROCESSED`.

> Aynı idempotency anahtarıyla ikinci kayıt açılmıyor; mevcut ticket geri dönüyor.

### 80–90 s — Close on measurement

Press **Metrikleri Yenile**. Show tickets created, duplicates prevented and median cycle time.

> Bu metrikler ayrı bir sayaçtan değil, audit trail'in kendisinden türetiliyor. Ölçemediğim şeyi iddia etmiyorum.

## B. Five-minute technical tour

### 1. The rejected path (0:00–0:50)

Analyze a request against a supplier whose status is not active. The decision is `REJECTED`, the citation is `SUP-COMP-2026 §2.1`, and `approval` is `null`.

> Reddedilen talepte onay kaydı hiç açılmıyor. Yani "onaylanırsa geçer" diye bir arka kapı yok; kural, akışı orada bitiriyor.

### 2. Injection is data (0:50–1:40)

Analyze the hero request with the untrusted supplier attachment in place. Show the quarantine banner, then the `SECURITY_CONTENT_QUARANTINED` audit event.

Then paste an injected instruction into the intake box and show that the draft still comes back with `injection_rule_id` set, and that nothing has been analyzed or executed.

> Saldırgan içerik ne karar bağlamına giriyor ne de bir aksiyon tetikliyor. Yalnızca veri olarak işaretleniyor ve iz bırakıyor.

### 3. Governed retrieval (1:40–2:50)

Ask, on request date `2026-08-18`:

```text
Finans yöneticisi onayı hangi tutarın üzerinde gerekir?
```

The top section is `PROC-POL-2026 §4.2`; the mode label reads `Sözcüksel arama` when no embedding index is present.

Now show what is missing from the results: the 2025 policy is superseded and the supplier attachment is untrusted, so neither is in the answer.

> Buradaki kritik nokta sıralama değil, aday havuzu. Yürürlük tarihi, rol ve güven filtreleri skorlamadan önce çalışıyor; bu yüzden hiçbir benzerlik puanı eski politikayı geri getiremiyor. `RAG-001` ve `RAG-002` bunu dondurulmuş eval olarak kontrol ediyor.

### 4. The audit trail (2:50–3:40)

Open the audit drawer and walk one trace ID end to end: `REQUEST_RECEIVED`, `POLICY_RETRIEVED`, `POLICY_EVALUATED`, `APPROVAL_REQUESTED`, `APPROVAL_GRANTED`, `TOOL_EXECUTED`. Show a denied attempt in the same list.

> Başarı da başarısızlık da aynı izde. Metrikler de bu izden türediği için ölçüm ile kanıt aynı kaynağı paylaşıyor.

### 5. What the pipeline proves (3:40–5:00)

Run the gate:

```bash
ruff check .
node --check app/static/app.js
pytest -q
python scripts/verify.py
python scripts/run_evals.py
```

202 tests, 9 project invariants, 15 frozen evaluation cases. Then unset the API key and run it again unchanged.

> Bütün bu doğrulama sağlayıcı anahtarı olmadan geçiyor. Model katmanı kapalıyken intake `503 LLM_DISABLED` dönüyor, anlatım ve cevap `null` oluyor, geri kalan her şey aynı kalıyor. Model değişimi tek konfigürasyon satırı, çünkü hiçbir kararın sahibi model değil.
