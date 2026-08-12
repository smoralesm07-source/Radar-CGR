from radar_cgr.semaforo import _status,parse_semaforo


def test_status_mapping():
    assert _status("DIP_ALCALDE","Sujeto obligado cumplió oportunamente con la presentación de su DIP")=="GREEN"
    assert _status("OTRAS_DIP","Tiene DIPs sin enviar emitidas hace más de 30 días")=="RED"
    assert _status("INFORMES_CONTABLES","Entre 99% a 50% de los informes contables enviados a Contraloría")=="YELLOW"
    assert _status("PERSONAL_TRANSPARENCIA","El municipio presenta incumplimiento significativo")=="RED"
    assert _status("ROYALTY_SUBDERE","No aplica, el municipio no recibió recursos provenientes del Royalty Minero")=="NA"


def test_parse_semaforo_table():
    html='''<table><thead><tr><th>Comuna</th><th>Región</th><th>DIP (08/07)</th><th>Otras (08/07)</th><th>Contables (20/07)</th><th>Pago (20/07)</th><th>Ingreso (20/07)</th><th>Caja (20/07)</th><th>Personal (11/08)</th><th>Royalty (06/08)</th></tr></thead><tbody><tr><td>IQUIQUE</td><td>REGION DE TARAPACA</td><td>Sujeto obligado cumplió oportunamente con la presentación de su DIP</td><td>No tiene DIPs pendientes de enviar o estas tienen menos de 20 días desde su emisión</td><td>100% todos los informes contables enviados a Contraloría</td><td>Refleja que el municipio ha pagado la totalidad de sus deudas de años anteriores</td><td>Refleja que el municipio ha percibido menos del 50% de sus ingresos de años anteriores</td><td>Refleja que el municipio no ha actualizado correctamente su presupuesto de Saldo Inicial de Caja</td><td>El municipio cumple con la obligación de reporte</td><td>El municipio ha informado a la SUBDERE los gastos ejecutados</td></tr></tbody></table>'''
    rows=parse_semaforo(html,"2026-08-12T18:00:00+00:00")
    assert len(rows)==8
    assert {x["commune"] for x in rows}=={"IQUIQUE"}
    assert rows[0]["snapshot_date"]=="2026-08-12"
    assert rows[0]["indicator_as_of_ddmm"]=="08/07"
