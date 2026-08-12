from radar_cgr.intelligence import (
    assess_penal,
    calculate_cgr_score,
    classify_irregularities,
    extract_providers,
    extract_public_organization,
    normalize_region,
)


def test_region_normalization():
    assert normalize_region("REGIONAL ANTOFAGASTA") == "Antofagasta"
    assert normalize_region("DE ARICA Y PARINACOTA. JUNIO 2026") == "Arica y Parinacota"
    assert normalize_region("BIO-BÍO") == "Biobío"


def test_extract_public_organization_from_objective():
    doc={"raw_text":"OBJETIVO Efectuar auditoría en la Comisión Nacional de Riego, CNR, a los pagos de bonificaciones. CONCLUSIONES 1. x"}
    assert extract_public_organization(doc,{}) == "Comisión Nacional de Riego"


def test_provider_extraction_company():
    text="La CNR contrató a la empresa Consultora Arrebol Ingeniería y Gestión del Agua SpA, por $357.262.000."
    providers=extract_providers(text)
    assert any("Arrebol" in x["name"] for x in providers)
    assert any(x["relationship_type"]=="CONTRACTOR" for x in providers)


def test_conflict_interest_generates_penal_hypothesis():
    text="La entidad contrató a Consultora Arrebol Ingeniería y Gestión del Agua SpA pese a una inhabilidad; el dueño era cónyuge de una funcionaria. Se instruyó procedimiento disciplinario."
    irr=classify_irregularities(text,"F1","D1","E1","https://www.contraloria.cl/x")
    codes={x.code for x in irr}
    assert "CONFLICT_INTEREST" in codes
    hyps=assess_penal(text,codes,["DISCIPLINARY"],357262000,"F1","D1","E1","https://www.contraloria.cl/x")
    assert any(x.code=="POTENTIAL_INCOMPATIBLE_NEGOTIATION" for x in hyps)
    assert max(x.score for x in hyps)>=75


def test_payment_without_service_generates_fraud_relevance():
    text="Se efectuó un pago improcedente de $500.000.000 por servicios cuya prestación no fue acreditada y CGR formulará reparo."
    irr=classify_irregularities(text,"F2","D2","E2","https://www.contraloria.cl/x")
    codes={x.code for x in irr}
    hyps=assess_penal(text,codes,["REPARO"],500000000,"F2","D2","E2","https://www.contraloria.cl/x")
    assert "PAYMENT_IMPROPER" in codes
    assert any(x.code=="POTENTIAL_FRAUD_AGAINST_STATE" for x in hyps)
    assert calculate_cgr_score(irr,["REPARO"],500000000)>=80


def test_explicit_mp_referral_is_marked_explicit():
    text="La Contraloría remitirá los antecedentes al Ministerio Público para los fines que correspondan."
    hyps=assess_penal(text,set(),["CRIMINAL_REFERRAL"],None,"F3","D3","E3","https://www.contraloria.cl/x")
    assert hyps
    assert hyps[0].evidence_level=="EXPLICIT_CGR_REFERRAL"
    assert hyps[0].relevance=="HIGH"
