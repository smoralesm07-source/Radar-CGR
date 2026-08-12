from radar_cgr.cic import extract_cic_articles


def test_extract_numbered_cic_and_datasets():
    rows=extract_cic_articles([{"url":"https://mantencion.contraloria.cl/x","title":"CIC 13: CGR verifica licencias","date":"30/06/2025","content_hash":"x","text_excerpt":"El decimotercer Consolidado de Información Circularizada cruzó información del Ministerio Público con SIAPER."}])
    assert len(rows)==1
    assert rows[0]["cic_number"]==13
    assert "SIAPER" in rows[0]["datasets_detected"]
    assert "MINISTERIO_PUBLICO" in rows[0]["datasets_detected"]


def test_extract_ordinal_cic():
    rows=extract_cic_articles([{"url":"https://mantencion.contraloria.cl/y","title":"registrados en SIAPER","date":"29/04/2025","content_hash":"y","text_excerpt":"A través del séptimo Consolidado de Información Circularizada, CGR comparó declaraciones de renta del Servicio de Impuestos Internos y SIAPER."}])
    assert rows[0]["cic_number"]==7
    assert set(rows[0]["datasets_detected"])>={"SIAPER","SII"}


def test_non_cic_is_ignored():
    assert extract_cic_articles([{"url":"x","title":"Auditoría CGR","text_excerpt":"Informe de auditoría"}])==[]
