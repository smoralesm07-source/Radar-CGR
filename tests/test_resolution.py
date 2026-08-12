from radar_cgr.resolution import (
    _split_compound_provider,
    clean_provider_name,
    infer_organization,
    plausible_org,
    provider_signature,
)


def test_rejects_non_institutional_false_positive():
    assert not plausible_org("s etapas de diseño")


def test_mun_villarrica_is_canonicalized():
    doc={"title":"INFORME FINAL MUN VILLARRICA SOBRE IRREGULARIDADES","raw_text":""}
    assert infer_organization(doc,"MUN VILLARRICA") == "Municipalidad de Villarrica"


def test_municipality_title_is_trimmed():
    doc={"title":"INFORME FINAL 187-26 MUNICIPALIDAD DE TIERRA AMARILLA INSPECCIÓN EN TERRENO SOBRE IRREGULARIDADES","raw_text":""}
    assert infer_organization(doc,"") == "MUNICIPALIDAD DE TIERRA AMARILLA"


def test_title_resolves_slep_and_objective_resolves_conaf():
    slep={"title":"INFORME FINAL, SERVICIO LOCAL DE EDUCACIÓN PÚBLICA DE AYSÉN, INSPECCIÓN EN TERRENO","raw_text":""}
    assert "SERVICIO LOCAL DE EDUCACIÓN PÚBLICA DE AYSÉN" == infer_organization(slep,"").upper()
    conaf={"title":"INFORME FINAL 154 DE 2026","raw_text":"OBJETIVO Verificar en terreno que la Corporación Nacional Forestal, a través de su Dirección Regional, haya ejecutado acciones. CONCLUSIONES x"}
    assert infer_organization(conaf,"") == "Corporación Nacional Forestal"


def test_provider_leading_connector_is_removed():
    assert clean_provider_name("de Four Service SpA") == "Four Service SpA"


def test_compound_provider_is_split():
    parts=_split_compound_provider("Constructora Guerra Letelier SpA y Four Service SpA")
    assert parts == ["Constructora Guerra Letelier SpA","Four Service SpA"]


def test_provider_signature_collapses_conjunction_variant():
    assert provider_signature("Constructora Guerra Letelier SpA") == provider_signature("Constructora Guerra y Letelier SpA")
