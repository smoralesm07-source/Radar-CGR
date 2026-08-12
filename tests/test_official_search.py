from radar_cgr.official_search import canonical_url, extract_hashes, month_windows, parse_result_count


def test_extract_hashes_from_modern_and_docidcm():
    h1="5f52f7d11546b51ec0441d3a666093f1"
    h2="060b001a7ebc963947a8732a3bd209ce"
    text=f'https://www.contraloria.cl/buscadorpdf/auditoria/{h1}/html docIdcm="{h2}"'
    assert extract_hashes(text)=={h1,h2}


def test_month_windows_are_month_complete():
    rows=month_windows(2024,2024,2)
    assert rows==[("2024-01","2024-01-01","2024-01-31"),("2024-02","2024-02-01","2024-02-29")]


def test_result_count_supports_chilean_thousands_separator():
    assert parse_result_count("Total 1.234 resultados") == 1234
    assert parse_result_count("0 informes") == 0


def test_canonical_url():
    h="318bf06bc86be907de40fb96696376a9"
    assert canonical_url(h).endswith(f"/{h}/html")
