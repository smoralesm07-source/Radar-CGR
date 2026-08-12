from radar_cgr.history import (
    _news_article_links,
    _pagination_links,
    audit_hash,
    canonical_audit_url,
    register_urls,
)


def test_canonical_audit_url():
    raw="https://www.contraloria.cl/buscadorpdf/auditoria/5F52F7D11546B51EC0441D3A666093F1/html?x=1"
    assert canonical_audit_url(raw)=="https://www.contraloria.cl/buscadorpdf/auditoria/5f52f7d11546b51ec0441d3a666093f1/html"
    assert audit_hash(raw)=="5f52f7d11546b51ec0441d3a666093f1"


def test_register_urls_deduplicates_by_hash():
    registry={}
    now="2026-08-12T18:00:00+00:00"
    urls={
        "https://www.contraloria.cl/buscadorpdf/auditoria/5f52f7d11546b51ec0441d3a666093f1/html",
        "https://www.contraloria.cl/buscadorpdf/auditoria/5F52F7D11546B51EC0441D3A666093F1/html?foo=bar",
    }
    assert register_urls(registry,urls,"TEST","https://www.contraloria.cl",now)==1
    assert len(registry)==1


def test_news_article_links_only_official_articles():
    html='''<a href="/cgr/web/cgr/noticias/-/asset_publisher/X/content/caso/index.html">Caso</a>
    <a href="https://otro.cl/noticias/x">No</a>'''
    rows=_news_article_links(html,"https://mantencion.contraloria.cl/cgr/web/cgr/noticias/index.html")
    assert len(rows)==1
    assert rows[0].startswith("https://mantencion.contraloria.cl/")


def test_pagination_links_detect_liferay_cur():
    html='''<a href="?p_p_id=101_INSTANCE_X&_101_INSTANCE_X_cur=2&_101_INSTANCE_X_delta=30">2</a>
    <a href="/cgr/web/cgr/noticias/-/asset_publisher/X/content/caso/index.html">Caso</a>'''
    rows=_pagination_links(html,"https://mantencion.contraloria.cl/cgr/web/cgr/noticias/index.html")
    assert len(rows)==1
    assert "cur=2" in rows[0]
