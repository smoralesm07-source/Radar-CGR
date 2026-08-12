from __future__ import annotations

import re
from dataclasses import dataclass

@dataclass(frozen=True)
class AMLAssessment:
    finding_type: str
    risk_family: str
    score: int
    relevance: str
    severity: str
    enforcement: list[str]

# Las reglas priorizan señales explicables. No equiparan una observación CGR con LA/FT.
RULES = [
    ("COI", "CONFLICT_OF_INTEREST", 78, [r"conflicto de inter[eé]s", r"incompatibil", r"inhabilidad", r"c[oó]nyuge.*(?:funcionari|contrat)", r"v[ií]nculo.*proveedor"]),
    ("FRA", "FRAUD_OR_MISAPPROPRIATION", 86, [r"fraude", r"malvers", r"desv[ií]o", r"falsific", r"servicios? no prestad", r"pagos? improcedent"]),
    ("PUB", "TRANSFER_OR_PUBLIC_FUNDS", 64, [r"transferenc", r"fondos? p[uú]blic", r"rendici[oó]n", r"subvenci", r"bonificaci", r"beneficiar"]),
    ("PROC", "PROCUREMENT", 66, [r"licitaci", r"trato directo", r"adjudic", r"proveedor", r"orden(?:es)? de compra", r"contrataci[oó]n"]),
    ("FIN", "FINANCIAL_ANOMALY", 60, [r"diferencia.*contabl", r"saldo.*moros", r"deuda", r"sin respaldo", r"no contabiliz", r"ingresos por percibir"]),
    ("AST", "ASSET_INCONSISTENCY", 67, [r"bienes? inmuebles?", r"veh[ií]culos?", r"inventario", r"activo", r"predio"]),
    ("CTL", "CONTROL_WEAKNESS", 45, [r"falta de control", r"debilidad(?:es)? de control", r"supervisi[oó]n", r"mecanismos? de control"]),
    ("PER", "PERSONNEL_INTEGRITY", 55, [r"funcionari", r"honorarios", r"remuneraci", r"licencia m[eé]dica"]),
    # No se usa "Fiscalía" a secas: CGR posee una Unidad de Seguimiento de Fiscalía,
    # que no debe confundirse con una derivación al Ministerio Público.
    ("CRM", "CRIMINAL_CONTEXT", 92, [r"antecedentes penales", r"ministerio p[uú]blico", r"fiscal regional(?: del ministerio p[uú]blico)?", r"pudieran? revestir.*car[aá]cter(?:es)? de delito", r"hechos?.*car[aá]cter(?:es)? de delito", r"marihuana", r"usurpaci[oó]n"]),
]

ENFORCEMENT = {
    "DISCIPLINARY": [r"procedimiento disciplinario", r"sumario(?: administrativo)?"],
    "REPARO": [r"reparo"],
    "CRIMINAL_REFERRAL": [r"(?:remit|puesto|pondr[aá]|comunic).*ministerio p[uú]blico", r"ministerio p[uú]blico.*(?:conocimiento|fines)", r"remit.*fiscal regional(?: del ministerio p[uú]blico)?"],
    "CDE_REFERRAL": [r"consejo de defensa del estado", r"\bCDE\b"],
    "FOLLOW_UP": [r"sistema de seguimiento", r"plazo de 60 d[ií]as", r"plazo de 15 d[ií]as"],
}


def assess(text: str, has_amount: bool = False) -> AMLAssessment:
    lower = (text or "").lower()
    best = ("GEN", "CONTROL_OR_COMPLIANCE", 30)
    matched_count = 0
    for code, family, base, patterns in RULES:
        local_matches = sum(bool(re.search(p, lower, re.I | re.S)) for p in patterns)
        if local_matches:
            matched_count += local_matches
            candidate = min(100, base + (local_matches - 1) * 4)
            if candidate > best[2]:
                best = (code, family, candidate)

    score = best[2]
    enforcement: list[str] = []
    for label, patterns in ENFORCEMENT.items():
        if any(re.search(p, text or "", re.I | re.S) for p in patterns):
            enforcement.append(label)

    if has_amount:
        score = min(100, score + 4)
    if "CRIMINAL_REFERRAL" in enforcement:
        score = min(100, score + 10)
    elif enforcement:
        score = min(100, score + 5)
    if matched_count >= 3:
        score = min(100, score + 4)

    relevance = "HIGH" if score >= 80 else "MEDIUM" if score >= 55 else "LOW"
    severity = "CRITICAL" if score >= 90 else "HIGH" if score >= 75 else "MEDIUM" if score >= 50 else "LOW"
    return AMLAssessment(best[0], best[1], score, relevance, severity, enforcement)
