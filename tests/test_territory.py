"""Resolución territorial contra el índice canónico del Context Hub."""

from radar_cgr.territory import match_key, resolve, territory_id


def test_canonical_region_name_resolves():
    assert resolve("Biobío", "REGION") == ("CL-REG-08", "VALIDATED_EXACT")
    assert resolve("Región de Los Lagos", "REGION")[0] == "CL-REG-10"


def test_spellings_that_the_private_table_missed():
    """Las dos glosas que el adaptador privado dejaba sin clave.

    El guion de «BIO-BÍO» y el apóstrofo de «O'Higgins» rompían la
    normalización anterior, que convertía la puntuación en espacio y luego
    comparaba contra claves sin espacio.
    """
    assert territory_id("BIO-BÍO", "REGION") == "CL-REG-08"
    assert territory_id("O'Higgins", "REGION") == "CL-REG-06"


def test_roman_numerals_resolve():
    assert territory_id("VIII", "REGION") == "CL-REG-08"
    assert territory_id("RM", "REGION") == "CL-REG-13"


def test_cut_code_passes_through():
    assert resolve("13", "REGION") == ("CL-REG-13", "CODE_EXACT")
    assert resolve("CL-REG-08", "REGION") == ("CL-REG-08", "CODE_EXACT")


def test_extraction_garbage_is_classified_not_guessed():
    """El texto arrastrado se distingue de un topónimo simplemente faltante."""
    garbage = "DE ARICA Y PARINACOTA. _JUNIO 2026_ Documento Asociado Descargar documento"
    assert resolve(garbage, "REGION") == (None, "NOT_A_PLACE_NAME")
    assert resolve(", oficina del SAG a cargo,", "REGION") == (None, "UNRESOLVED_NAME_ONLY")


def test_empty_is_unknown_not_unresolved():
    assert resolve(None, "REGION") == (None, "UNKNOWN")
    assert resolve("   ", "REGION") == (None, "UNKNOWN")


def test_no_fuzzy_promotion():
    for text in ("Bío", "Biobio Sur", "Metropolit", "Region"):
        assert territory_id(text, "REGION") is None


def test_commune_level_is_separate_from_region():
    """«Los Lagos» es región y además comuna de la Región de Los Ríos."""
    assert territory_id("Los Lagos", "REGION") == "CL-REG-10"
    assert territory_id("Los Lagos", "COMMUNE") == "CL-COM-14104"


def test_key_recipe_matches_the_hub():
    assert match_key("Región del Biobío") == "BIOBIO"
    assert match_key("O'Higgins") == "OHIGGINS"
