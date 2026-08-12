from radar_cgr.commoncrawl_discovery import extract_hash, official_url


def test_extract_hash_from_legacy_docid():
    url="http://www.contraloria.cl/SicaProd/SICAv3-BIFAPortalCGR/faces/detalleInforme?docIdcm=fce8fa4b8f48ac9abf4962b4a2558ca8&_adf.ctrl-state=x"
    assert extract_hash(url)=="fce8fa4b8f48ac9abf4962b4a2558ca8"


def test_extract_hash_removes_linewrap_hyphen():
    url="http://www.contraloria.cl/SicaProd/SICAv3-BI-FAPortalCGR/faces/detalleInforme?docIdcm=09c-f4f51c7dcf785b2535d8539610313"
    assert extract_hash(url)=="09cf4f51c7dcf785b2535d8539610313"


def test_extract_hash_from_modern_url():
    url="https://www.contraloria.cl/buscadorpdf/auditoria/5f52f7d11546b51ec0441d3a666093f1/html"
    assert extract_hash(url)=="5f52f7d11546b51ec0441d3a666093f1"
    assert official_url(extract_hash(url)).endswith("/5f52f7d11546b51ec0441d3a666093f1/html")
