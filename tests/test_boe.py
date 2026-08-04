# tests/test_boe.py
import pytest
from unittest.mock import patch, MagicMock
from src.boe import fetch_boe_sumario, extract_boe_items, fetch_boe_entry

SAMPLE_SUMARIO = {
    "status": {"code": "200", "text": "ok"},
    "data": {
        "sumario": {
            "metadatos": {"publicacion": "BOE", "fecha_publicacion": "20260515"},
            "diario": [
                {
                    "numero": "118",
                    "seccion": [
                        {
                            "codigo": "1",
                            "nombre": "I. Disposiciones generales",
                            "departamento": [
                                {
                                    "nombre": "MINISTERIO DE HACIENDA",
                                    "epigrafe": [
                                        {
                                            "nombre": "Tributos",
                                            "item": {
                                                "identificador": "BOE-A-2026-001",
                                                "titulo": "Real Decreto sobre IRPF",
                                                "url_xml": "https://www.boe.es/diario_boe/xml.php?id=BOE-A-2026-001"
                                            }
                                        },
                                        {
                                            "nombre": "Vivienda",
                                            "item": [
                                                {
                                                    "identificador": "BOE-A-2026-002",
                                                    "titulo": "Ley de vivienda accesible",
                                                    "url_xml": "https://www.boe.es/diario_boe/xml.php?id=BOE-A-2026-002"
                                                },
                                                {
                                                    "identificador": "BOE-A-2026-003",
                                                    "titulo": "Real Decreto de alquiler",
                                                    "url_xml": "https://www.boe.es/diario_boe/xml.php?id=BOE-A-2026-003"
                                                }
                                            ]
                                        }
                                    ]
                                }
                            ]
                        },
                        {
                            "codigo": "3",
                            "nombre": "III. Otras disposiciones",
                            "departamento": [
                                {
                                    "nombre": "MINISTERIO DE DEFENSA",
                                    "epigrafe": [
                                        {
                                            "nombre": "Convocatorias",
                                            "item": {
                                                "identificador": "BOE-A-2026-999",
                                                "titulo": "Convocatoria oposiciones",
                                                "url_xml": "https://www.boe.es/diario_boe/xml.php?id=BOE-A-2026-999"
                                            }
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    }
}

SAMPLE_ENTRY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<documento>
  <metadatos>
    <identificador>BOE-A-2026-001</identificador>
    <rango>Real Decreto</rango>
    <departamento>Ministerio de Hacienda</departamento>
  </metadatos>
  <texto>El presente Real Decreto regula la fiscalidad de las rentas del trabajo en España.</texto>
</documento>"""


def test_extract_items_only_sections_1_and_2():
    items = extract_boe_items(SAMPLE_SUMARIO)
    ids = [i["identificador"] for i in items]
    assert "BOE-A-2026-001" in ids
    assert "BOE-A-2026-002" in ids
    assert "BOE-A-2026-003" in ids
    assert "BOE-A-2026-999" not in ids


def test_extract_items_handles_single_item_as_dict():
    items = extract_boe_items(SAMPLE_SUMARIO)
    assert any(i["identificador"] == "BOE-A-2026-001" for i in items)


def test_extract_items_handles_multiple_items_as_list():
    items = extract_boe_items(SAMPLE_SUMARIO)
    ids = [i["identificador"] for i in items]
    assert "BOE-A-2026-002" in ids
    assert "BOE-A-2026-003" in ids


def test_extract_items_includes_fecha_and_departamento():
    items = extract_boe_items(SAMPLE_SUMARIO)
    item = next(i for i in items if i["identificador"] == "BOE-A-2026-001")
    assert item["fecha"] == "20260515"
    assert item["departamento"] == "MINISTERIO DE HACIENDA"


def test_fetch_boe_sumario_returns_data_on_200():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = SAMPLE_SUMARIO
    with patch("src.boe.requests.get", return_value=mock_resp):
        result = fetch_boe_sumario("20260515")
    assert result is not None
    assert "data" in result


def test_fetch_boe_sumario_returns_none_on_404():
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    with patch("src.boe.requests.get", return_value=mock_resp):
        result = fetch_boe_sumario("20260515")
    assert result is None


def test_fetch_boe_sumario_returns_none_on_network_error():
    with patch("src.boe.requests.get", side_effect=Exception("timeout")):
        result = fetch_boe_sumario("20260515")
    assert result is None


def test_fetch_boe_entry_returns_rango_and_preview():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = SAMPLE_ENTRY_XML
    with patch("src.boe.requests.get", return_value=mock_resp):
        result = fetch_boe_entry("https://www.boe.es/diario_boe/xml.php?id=BOE-A-2026-001")
    assert result is not None
    assert result["rango"] == "Real Decreto"
    assert "fiscalidad" in result["texto_preview"]


def test_fetch_boe_entry_returns_none_on_error():
    with patch("src.boe.requests.get", side_effect=Exception("timeout")):
        result = fetch_boe_entry("https://www.boe.es/diario_boe/xml.php?id=BOE-A-2026-001")
    assert result is None


def test_fetch_boe_sumario_returns_none_on_json_error():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.side_effect = ValueError("not json")
    with patch("src.boe.requests.get", return_value=mock_resp):
        result = fetch_boe_sumario("20260515")
    assert result is None


def test_digest_boe_solo_incluye_rangos_con_fuerza_de_ley(tmp_path):
    from src.db import init_db, get_conn, insert_boe_entry, get_boe_for_digest
    db = tmp_path / "b.db"
    init_db(db)
    conn = get_conn(db)
    casos = [
        ("BOE-A-1", "Ley 5/2026 de vivienda", "Ley"),
        ("BOE-A-2", "Ley Orgánica 2/2026", "Ley Orgánica"),
        ("BOE-A-3", "Real Decreto-ley 9/2026", "Real Decreto-ley"),
        ("BOE-A-4", "Real Decreto 300/2026 de nombramiento", "Real Decreto"),
        ("BOE-A-5", "Resolución de la Subsecretaría", "Resolución"),
        ("BOE-A-6", "Ley Foral 3/2026 de Navarra", "Ley Foral"),
    ]
    for ident, titulo, rango in casos:
        insert_boe_entry(conn, ident, titulo, rango, "Dpto", "20260714",
                         "url", ["vivienda"], "texto")

    idents = {r["identificador"] for r in get_boe_for_digest(conn)}
    assert idents == {"BOE-A-1", "BOE-A-2", "BOE-A-3"}
    conn.close()
