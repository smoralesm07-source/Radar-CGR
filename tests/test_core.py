from radar_cgr.aml import assess
from radar_cgr.extract import extract_audit_links, parse_audit_detail
from radar_cgr.models import stable_id
from radar_cgr.utils import normalize_name, parse_clp_amounts


def test_stable_id_is_idempotent():
    assert stable_id("EVT","a",1)==stable_id("EVT","a",1)
    assert stable_id("EVT","a",1)!=stable_id("EVT","a",2)


def test_normalize_name(): assert normalize_name("Constructora Águila SpA")=="CONSTRUCTORA AGUILA SPA"

def test_parse_clp_amounts(): assert parse_clp_amounts("monto de $1.234.567 y $ 9.000")==[1234567,9000]


def test_aml_rule_enforcement():
    a=assess("Se detectó conflicto de interés y se instruyó un procedimiento disciplinario.",False)
    assert a.relevance in {"MEDIUM","HIGH"}; assert "DISCIPLINARY" in a.enforcement


def test_cgr_fiscalia_is_not_criminal_referral():
    a=assess("Se remitirá el acto a la Unidad de Seguimiento de Fiscalía de la Contraloría General.",False)
    assert "CRIMINAL_REFERRAL" not in a.enforcement
    assert a.risk_family!="CRIMINAL_CONTEXT"


def test_ministerio_publico_is_criminal_referral():
    a=assess("El informe será puesto en conocimiento del Ministerio Público para los fines que correspondan.",False)
    assert "CRIMINAL_REFERRAL" in a.enforcement
    assert a.risk_family=="CRIMINAL_CONTEXT"


def test_extract_audit_links():
    html='<a href="https://www.contraloria.cl/buscadorpdf/auditoria/abc123/html">informe</a>'
    assert extract_audit_links(html)==["https://www.contraloria.cl/buscadorpdf/auditoria/abc123/html"]


def test_parse_audit_structured_metadata_and_entity():
    html="""<html><body><div>AUDITORIA - Número: undefined</div><h4>INFORME FINAL 454-25 COMISIÓN NACIONAL DE RIEGO SOBRE AUDITORÍA</h4><div>NÚMERO<br>454/2025<br>FECHA DOCUMENTO<br>06-06-2026<br>NIVEL<br>:<br>CENTRAL<br>UNIDAD CGR<br>:<br>I CONTRALORÍA REGIONAL METROPOLITANA DE SANTIAGO<br>TIPO<br>:<br>INFORME FINAL DE AUDITORÍA DE CUMPLIMIENTO<br>REGIÓN<br>:<br>METROPOLITANA DE SANTIAGO<br>NOMBRE<br>:<br>INFORME FINAL 454-25 COMISIÓN NACIONAL DE RIEGO SOBRE AUDITORÍA</div><h4>OBJETIVO</h4><p>Efectuar auditoría en la Comisión Nacional de Riego, CNR, a los pagos de bonificaciones.</p><h4>CONCLUSIONES</h4><p>1. Se detectó un pago improcedente de $51.950.000 y se instruyó procedimiento disciplinario.</p><p>2. El informe será puesto en conocimiento del Ministerio Público para los fines que correspondan.</p></body></html>"""
    r=parse_audit_detail(html,"https://www.contraloria.cl/buscadorpdf/auditoria/abcdef123456/html")
    assert r.document.document_number=="454/2025"
    assert r.document.region.upper().startswith("METROPOLITANA")
    assert r.document.document_type.startswith("INFORME FINAL")
    assert r.event.entity_name=="Comisión Nacional de Riego"
    assert any(x.aml_relevance=="HIGH" for x in r.findings)
    assert all(x.evidence_id for x in r.findings)
