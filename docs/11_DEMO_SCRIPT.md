# Demo Script

## 90-second hiring demo

### 0–10 seconds — Start with the process

Show the as-is chain:

```text
Email → PDF policy → Excel → Finance email → Jira/ERP
```

Voiceover:

> Bu projeye chatbot geliştirerek değil, kurgusal müşterinin satın alma istisna sürecini haritalandırarak başladım.

### 10–20 seconds — Explain the engineering boundary

Show:

```text
AI explains
Code calculates
Human approves
API executes
Audit proves
```

Voiceover:

> Kritik hesapları, yetkiyi ve politika kararını LLM'ye bırakmadım. Model ancak yapılandırılmış sonucu açıklayabilir.

### 20–47 seconds — Analyze the request

Submit PR-2026-0042 and show:

- 220,000 TRY request
- 184,500 TRY median
- 19.2% variance
- One missing quote
- Expired ISO certificate
- Finance approval required

### 47–59 seconds — Show evidence

Show current policy v2026.1 and its sections. Briefly show v2025.2 as superseded.

Voiceover:

> Sistem talep tarihinde geçerli politika sürümünü seçiyor ve kararın hangi bölümlerden geldiğini gösteriyor.

### 59–72 seconds — Human approval

Show the action preview and approve as finance user.

> Hiçbir write action açık insan onayı olmadan çalışmıyor.

### 72–82 seconds — Execute twice

Create the MockDesk ticket, then execute again.

> Aynı idempotency key ile ikinci kayıt oluşmuyor; mevcut ticket geri dönüyor.

### 82–90 seconds — Close with audit and role fit

Show audit events.

> Bu yalnızca çalışan bir agent değil; süreç keşfinden kontrollü kurumsal aksiyona ve handoff'a uzanan bir Forward-Deployed Solution Engineering vaka çalışması.

## Four-minute technical walkthrough

1. Business process and scope boundary
2. File and data model
3. Current-policy retrieval
4. Decimal calculations
5. Deterministic policy engine
6. Approval state
7. MockDesk HTTP and idempotency
8. Injection test
9. Audit reconstruction
10. SkyStudio workflow mapping and limitations
