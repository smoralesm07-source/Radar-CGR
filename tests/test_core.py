from radar_cgr.aml import assess
from radar_cgr.extract import extract_audit_links, parse_audit_detail
from radar_cgr.models import stable_id
from radar_cgr.utils import normalize_name, parse_clp_amounts


def test_stable_id_is_idempotent():
    assert stable_id("EVT", "a", 1) == stable_id("EVT", "a", 1)
    assert stable_id("EVT", "a", 1) != stable_id("EVT", "a", 2)


def test_normalize_name():
    assert normalize_name("Constructora Águila SpA") == "CONSTRUCTORA AGUILA SPA"


def test_parse_clp_amounts():
    assert parse_clp_amounts("monto de $1.234.567 y $ 9.000") == [1234567, 9000]


def test_aml_rule_enforcement():
    a = assess("Se detectó conflicto de interés y se instruyó un procedimiento disciplinario.", False)
    assert a.relevance in {"MEDIUM", "HIGH"}
    assert "DISCIPLINARY" in a.enforcement


def test_extract_audit_links():
    html = '<a href="https://www.contraloria.cl/buscadorpdf/auditoria/abc123/html">informe</a>'
    assert extract_audit_links(html) == ["https://www.contraloria.cl/buscadorpdf/auditoria/abc123/html"]


def test_parse_audit_minimal():
    html = """
    <html><body><h4>INFORME FINAL N°80-2026-INDAP-AUDITORÍA</h4><div>NÚMERO 80/2026 FECHA DOCUMENTO 08-05-2026 NIVEL:CENTRAL UNIDAD CGR:METROPOLITANA TIPO:INFORME FINAL DE AUDITORÍA DE CUMPLIMIENTO REGIÓN:METROPOLITANA NOMBRE:INFORME FINAL N°80-2026-INDAP-AUDITORÍA</div><h4>OBJETIVO</h4><p>Revisar el otorgamiento de créditos.</p><h4>CONCLUSIONES</h4><p>1) Se detectó falta de control sobre créditos por un total de $51.950.000 y se instruyó procedimiento disciplinario.</p><p>2) Se constataron antecedentes penales vinculados a beneficiarios y se informó a Fiscalía.</p></body></html>
    """
    result = parse_audit_detail(html, "https://www.contraloria.cl/buscadorpdf/auditoria/abcdef123456/html")
    assert result.document.document_number.startswith("80/2026")
    assert result.event.event_type == "AUDIT_REPORT"
    assert len(result.findings) >= 1
    assert any(x.aml_relevance == "HIGH" for x in result.findings)
    assert all(x.evidence_id for x in result.findings)
