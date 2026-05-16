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
