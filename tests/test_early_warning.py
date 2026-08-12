from radar_cgr.early_warning import extract_watch_candidates, _similarity


def test_extract_fiscalization_watch_candidate():
    html='<html><body><ul><li><a href="/web/cgr/fiscalizacion-x">Fiscalización en curso sobre compras públicas del Hospital Regional</a></li></ul></body></html>'
    rows=extract_watch_candidates("cgr_fiscalizaciones","https://www.contraloria.cl/web/cgr/fiscalizaciones-en-curso",html,"2026-08-12T12:00:00+00:00")
    assert len(rows)==1
    assert rows[0]["watch_type"]=="FISCALIZATION"
    assert rows[0]["stage"]=="WATCH"


def test_watch_similarity_requires_meaningful_overlap():
    a="Fiscalización sobre compras públicas del Hospital Regional de Antofagasta"
    b="Informe final Hospital Regional de Antofagasta sobre auditoría a compras públicas"
    assert _similarity(a,b)>=0.62
    assert _similarity(a,"Municipalidad de Villarrica jornada laboral")<0.62
