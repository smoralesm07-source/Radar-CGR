from radar_cgr.tribunal import extract_tribunal_cases


def test_extract_tribunal_state_daily_row():
    html='''<table><tr><th>Fecha</th><th>Rol</th><th>Nº Resolución</th><th>Nº Resolución</th><th>Demandante</th><th>Cuentadantes o Demandados</th></tr><tr><td>11/08/2026</td><td>65/2026</td><td>RES. Nº 91114</td><td>RES. Nº 91114</td><td>División de Gobiernos Regionales y Municipalidades</td><td>ARELLANO QUIROGA, CALDERÓN ARRIAGADA</td></tr></table>'''
    rows=extract_tribunal_cases(html,"https://www.contraloria.cl/transopencgrapp/publicadorJuicio/busquedaEstadoD","2026-08-12T12:00:00+00:00")
    assert len(rows)==1
    assert rows[0]["state_date"]=="2026-08-11"
    assert rows[0]["role"]=="65/2026"
    assert "91114" in rows[0]["resolution"]
    assert "Gobiernos Regionales" in rows[0]["claimant"]
    assert "ARELLANO" in rows[0]["defendants_raw"]


def test_extract_tribunal_from_rendered_text_fallback():
    html='''<html><body><div>Resultados 10 resultados Fecha Rol Nº Resolución Nº Resolución Demandante Cuentadantes o Demandados 11/08/2026 65/2026 RES. Nº 91114 RES. Nº 91114 División de Gobiernos Regionales y Municipalidades ARELLANO QUIROGA, CALDERÓN ARRIAGADA, FUENTES ASTORGA 11/08/2026 14/2026 RES. Nº 91119 RES. Nº 91119 Contraloría Regional de Los Ríos BORNECK LOAIZA, CAÑOLES PEÑA</div></body></html>'''
    rows=extract_tribunal_cases(html,"https://www.contraloria.cl/transopencgrapp/publicadorJuicio/busquedaEstadoD","2026-08-12T12:00:00+00:00")
    assert len(rows)==2
    assert rows[0]["role"]=="65/2026"
    assert "ARELLANO" in rows[0]["defendants_raw"]
    assert rows[1]["claimant"]=="Contraloría Regional de Los Ríos"
    assert "BORNECK" in rows[1]["defendants_raw"]
