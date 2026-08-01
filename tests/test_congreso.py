import pytest
from pathlib import Path
from src.congreso import parse_vote_xml, aggregate_group_votes, compute_resultado

FIXTURE_XML = (Path(__file__).parent / "fixtures" / "vote_session.xml").read_text(encoding="utf-8")


def test_parse_vote_xml_extracts_metadata():
    vote = parse_vote_xml(FIXTURE_XML)
    assert vote["sesion"] == 177
    assert vote["numero_votacion"] == 1
    assert vote["titulo"] == "Proposición de Ley de regularización extraordinaria"
    assert "arraigo laboral" in vote["texto_expediente"]


def test_parse_vote_xml_aggregates_by_group():
    vote = parse_vote_xml(FIXTURE_XML)
    groups = vote["group_votes"]

    assert groups["GP"]["voto"] == "No"
    assert groups["GS"]["voto"] == "Sí"
    assert groups["GSUMAR"]["voto"] == "Sí"
    assert groups["GVOX"]["voto"] == "No"


def test_divided_group_detected_when_dissent_exceeds_10_percent():
    # GP has 3 No + 1 Sí = 25% dissent → divided
    vote = parse_vote_xml(FIXTURE_XML)
    assert vote["group_votes"]["GP"]["divided"] is True


def test_unanimous_group_not_marked_divided():
    # GS has 3 Sí, no dissent
    vote = parse_vote_xml(FIXTURE_XML)
    assert vote["group_votes"]["GS"]["divided"] is False


def test_compute_resultado_aprobada():
    from src.congreso import compute_resultado
    assert compute_resultado(a_favor=310, en_contra=33) == "aprobada"


def test_compute_resultado_rechazada():
    from src.congreso import compute_resultado
    assert compute_resultado(a_favor=33, en_contra=310) == "rechazada"


def test_compute_resultado_empate_es_rechazada():
    from src.congreso import compute_resultado
    assert compute_resultado(a_favor=100, en_contra=100) == "rechazada"


def test_fixture_totals_parsed():
    vote = parse_vote_xml(FIXTURE_XML)
    assert vote["a_favor"] > 0 or vote["en_contra"] > 0


def test_aggregate_group_votes_majority_wins():
    raw = [
        {"grupo": "GP", "voto": "No"},
        {"grupo": "GP", "voto": "No"},
        {"grupo": "GP", "voto": "Sí"},
        {"grupo": "GS", "voto": "Sí"},
    ]
    result = aggregate_group_votes(raw)
    assert result["GP"]["voto"] == "No"
    assert result["GP"]["total"] == 3
    assert result["GS"]["voto"] == "Sí"


import zipfile
from pathlib import Path

FIXTURE_ZIP = Path(__file__).parent / "fixtures" / "sesion192.zip"


def _xml_from_zip(numero):
    with zipfile.ZipFile(FIXTURE_ZIP) as zf:
        for name in zf.namelist():
            if name.endswith(f"votacion{numero}.xml"):
                return zf.read(name).decode("utf-8", "replace")
    raise AssertionError(f"votacion{numero} no está en el fixture")


def test_parse_extrae_subgrupo_de_enmienda():
    vote = parse_vote_xml(_xml_from_zip(20))
    assert "Euskal Herria Bildu" in vote["titulo_subgrupo"]
    assert vote["texto_subgrupo"] == "Enmienda 270."


def test_votacion_de_conjunto_no_tiene_subgrupo():
    vote = parse_vote_xml(_xml_from_zip(54))
    assert vote["titulo_subgrupo"] == ""
    assert vote["texto_subgrupo"] == ""


def test_votacion_de_conjunto_de_la_ley_de_discapacidad_fue_aprobada():
    vote = parse_vote_xml(_xml_from_zip(54))
    assert vote["a_favor"] == 179
    assert vote["en_contra"] == 33
    assert compute_resultado(vote["a_favor"], vote["en_contra"]) == "aprobada"


def test_clasifica_sustantiva_cuando_no_hay_subgrupo():
    from src.congreso import classify_vote
    assert classify_vote("") == "sustantiva"


def test_clasifica_enmienda_a_la_totalidad_como_sustantiva():
    from src.congreso import classify_vote
    assert classify_vote("Enmiendas a la totalidad de texto alternativo.") == "sustantiva"


def test_clasifica_enmienda_parcial_como_parcial():
    from src.congreso import classify_vote
    assert classify_vote("Enmiendas presentadas por el Grupo Parlamentario VOX") == "parcial"


def test_clasifica_correccion_tecnica_como_parcial():
    from src.congreso import classify_vote
    assert classify_vote("Corrección técnica.") == "parcial"


def test_sesion_192_produce_7_sustantivas_de_56_votaciones():
    from src.congreso import classify_vote
    import zipfile
    with zipfile.ZipFile(FIXTURE_ZIP) as zf:
        xmls = [zf.read(n).decode("utf-8", "replace")
                for n in zf.namelist() if n.endswith(".xml")]
    clases = [classify_vote(parse_vote_xml(x)["titulo_subgrupo"]) for x in xmls]
    assert len(clases) == 56
    assert clases.count("sustantiva") == 7


def test_expediente_key_agrupa_el_dictamen_con_sus_enmiendas():
    from src.congreso import expediente_key
    enmienda = expediente_key("Proyecto de Ley por la que se modifican el Texto Refundido")
    conjunto = expediente_key("Votación del dictamen del Proyecto de Ley por la que se modifican el Texto Refundido")
    assert enmienda == conjunto


def test_expediente_key_normaliza_espacios_y_mayusculas():
    from src.congreso import expediente_key
    assert expediente_key("  Proyecto   de LEY X ") == expediente_key("proyecto de ley x")
