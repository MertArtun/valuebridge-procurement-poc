from app.models import PolicyDecision, PurchaseAnalysis


def explain_decision(decision: PolicyDecision, analysis: PurchaseAnalysis) -> str:
    lines = [f"Karar: {decision.decision_status}"]
    lines.extend(f"- {reason}" for reason in decision.blocking_reasons)
    lines.extend(f"- Uyarı: {warning}" for warning in decision.warnings)
    lines.append(
        f"- Hesaplama: geçmiş medyan {analysis.historical_median_try} TL, "
        f"fiyat sapması %{analysis.display_variance_percent}."
    )
    return "\n".join(lines)
