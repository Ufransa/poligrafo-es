# tests/electoral/test_fuentes.py
from pathlib import Path

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "electoral"


def test_la_devolucion_de_la_ley_de_lobbies_enlaza_su_texto_en_el_bocg(cli, zips):
    cli("descargar", "--zips", zips)
    cli("fuentes", "--iniciativas", str(FIX / "iniciativas_muestra.json"), "--boe", str(FIX / "boe_muestra.json"))
    v = next(v for v in cli("exportar")["votaciones"] if "grupos de interés" in v["expediente"] and v["subtipo"] == "devolucion")
    assert v["url_bocg"].startswith("https://www.congreso.es/public_oficiales/L15/CONG/BOCG/")


def test_la_convalidacion_de_un_decreto_ley_enlaza_el_boe(cli, zips):
    cli("descargar", "--zips", zips)
    cli("fuentes", "--iniciativas", str(FIX / "iniciativas_muestra.json"), "--boe", str(FIX / "boe_muestra.json"))
    v = next(v for v in cli("exportar")["votaciones"] if v["clave_iniciativa"] == "real decreto-ley 3/2026" and not v["excluida_tramite"])
    assert v["url_boe"].startswith("https://www.boe.es/")


def test_una_mocion_no_inventa_enlaces(cli, zips):
    cli("descargar", "--zips", zips)
    cli("fuentes", "--iniciativas", str(FIX / "iniciativas_muestra.json"), "--boe", str(FIX / "boe_muestra.json"))
    for v in cli("exportar")["votaciones"]:
        if v["tipo"].startswith("Mociones"):
            assert v["url_boe"] is None
