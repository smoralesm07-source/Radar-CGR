import re
from radar_cgr.fau import FAU_CATALOG


def _codes(text):
    return {x["pattern_code"] for x in FAU_CATALOG if any(re.search(p,text,re.I|re.S) for p in x["patterns"])}


def test_fau_procurement_and_supplier_payment_patterns():
    text="Se detectó trato directo con proveedor y un pago improcedente respaldado por facturas observadas."
    codes=_codes(text)
    assert "FAU_ADQUISICIONES" in codes
    assert "FAU_PAGO_PROVEEDORES" in codes


def test_fau_working_time_pattern():
    assert "FAU_HORAS_JORNADA" in _codes("Se verificó incumplimiento del control horario y jornada laboral.")
