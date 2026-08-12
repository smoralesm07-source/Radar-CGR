from radar_cgr.temporality import infer_occurrence_interval, normalize_document_date


def test_exact_occurrence_date():
    x=infer_occurrence_interval("Se verificó la reducción de jornada del día 6 de marzo de 2026.")
    assert x["occurrence_date_from"]=="2026-03-06"
    assert x["occurrence_date_to"]=="2026-03-06"
    assert x["occurrence_date_precision"]=="EXACT"


def test_shared_year_range():
    x=infer_occurrence_interval("La auditoría comprendió entre el 1 de enero y el 31 de diciembre de 2024.")
    assert x["occurrence_date_from"]=="2024-01-01"
    assert x["occurrence_date_to"]=="2024-12-31"
    assert x["occurrence_date_precision"]=="RANGE"


def test_year_range():
    x=infer_occurrence_interval("La empresa prestó servicios durante los años 2023 y 2024.")
    assert x["occurrence_date_from"]=="2023-01-01"
    assert x["occurrence_date_to"]=="2024-12-31"


def test_year_occurrence():
    x=infer_occurrence_interval("Durante el año 2024 se emitieron boletas de honorarios.")
    assert x["occurrence_date_precision"]=="YEAR"
    assert x["occurrence_date_from"]=="2024-01-01"


def test_inherits_audit_period_without_using_report_date():
    x=infer_occurrence_interval("Se detectaron debilidades de control.","La revisión comprendió entre el 1 de enero de 2023 y el 31 de diciembre de 2025.","29-05-2026")
    assert x["occurrence_date_from"]=="2023-01-01"
    assert x["occurrence_date_to"]=="2025-12-31"
    assert x["occurrence_date_precision"]=="AUDIT_RANGE"
    assert x["occurrence_date_anchor"]!="2026-05-29"


def test_unknown_never_falls_back_to_report_publication_date():
    x=infer_occurrence_interval("Se detectó una observación sin referencia temporal.","","29-05-2026")
    assert x["occurrence_date_precision"]=="UNKNOWN"
    assert x["occurrence_date_from"]==""


def test_normalize_document_date():
    assert normalize_document_date("29-05-2026")=="2026-05-29"
