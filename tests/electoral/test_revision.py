"""Pruebas de los hallazgos de la revisión final (2026-10-07)."""
import os
from pathlib import Path

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "electoral"


def _env(**extra):
    return {**os.environ, "ELECTORAL_LLM_FALSO": str(FIX / "llm_falso.py"), **extra}


def _votacion(datos, vid):
    return next(v for v in datos["votaciones"] if v["id"] == vid)


# --- Hallazgo 1: votaciones parciales (enmiendas, puntos sueltos) ---

def test_votar_no_a_una_enmienda_no_es_cambiar_de_postura_sobre_la_ley(cli, zips):
    cli("descargar", "--zips", zips)
    datos = cli("exportar")
    assert _votacion(datos, "101-1")["subtipo"] == "parcial"
    for partido in ("PSOE", "Sumar"):
        pares = datos["coherencia"].get(partido, [])
        assert not [p for p in pares if "101-1" in (p["a_favor"], p["en_contra"])], partido


def test_puntos_sueltos_de_una_mocion_no_son_cambios_de_postura(cli, zips):
    cli("descargar", "--zips", zips)
    datos = cli("exportar")
    ids = {"101-6", "101-8", "164-13", "164-17"}
    for partido, pares in datos["coherencia"].items():
        assert not [p for p in pares if {p["a_favor"], p["en_contra"]} <= ids], partido


def test_las_votaciones_parciales_no_se_juzgan(cli, zips):
    cli("descargar", "--zips", zips)
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf"), env=_env())
    cli("extraer", env=_env())
    cli("juzgar", "--k", "3", env=_env())
    datos = cli("exportar")
    parciales = {v["id"] for v in datos["votaciones"] if v["subtipo"] == "parcial"}
    assert parciales and not [c for c in datos["cruces"] if c["votacion_id"] in parciales]


# --- Hallazgo 3: una enmienda aprobada no es una ley en el BOE ---

def test_una_enmienda_aprobada_no_aparece_en_gobierno_ni_enlaza_el_boe(cli, zips, tmp_path):
    import json
    cli("descargar", "--zips", zips)
    clave = _votacion(cli("exportar"), "101-20")["clave_iniciativa"]
    boe = tmp_path / "boe.json"
    boe.write_text(json.dumps({clave: "BOE-A-2025-00001"}), encoding="utf-8")   # la ley sí está en el BOE
    cli("fuentes", "--iniciativas", str(FIX / "iniciativas_muestra.json"), "--boe", str(boe))
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf"), env=_env())
    cli("extraer", env=_env())
    cli("juzgar", "--k", "3", env=_env())
    datos = cli("exportar")
    assert _votacion(datos, "101-20")["url_boe"] is None
    assert not [g for g in datos["gobierno"].get("PSOE", []) if g["votacion_id"] == "101-20"]


# --- Hallazgo 2: las ausencias no son votos ---

def test_una_ausencia_no_convierte_a_un_partido_en_dividido(cli, zips):
    cli("descargar", "--zips", zips)
    assert _votacion(cli("exportar"), "101-1")["votos"]["ERC"]["dividido"] is False


def test_un_partido_que_no_vota_no_aparece_como_si_hubiera_votado(cli, zips):
    cli("descargar", "--zips", zips)
    for v in cli("exportar")["votaciones"]:
        assert all(x["voto"] != "No vota" for x in v["votos"].values()), v["id"]


# --- Hallazgo 4: mayorías cualificadas y asentimiento ---

def _zip_sintetico(destino, votaciones):
    """ZIP con XML reales de plantilla y las cabeceras cambiadas: dos casos límite que el Congreso no da juntos."""
    import re
    import zipfile
    plantilla = zipfile.ZipFile(next((FIX / "zips").glob("VOT_20250325*.zip")))
    xml = plantilla.read(plantilla.namelist()[0]).decode("iso-8859-1")
    destino.mkdir()
    with zipfile.ZipFile(destino / "VOT_20990101000000.zip", "w") as z:
        for n, (expediente, asent, si, no) in enumerate(votaciones, 1):
            x = re.sub(r"<NumeroVotacion>\d+</NumeroVotacion>", f"<NumeroVotacion>{n}</NumeroVotacion>", xml)
            x = re.sub(r"<TextoExpediente>.*?</TextoExpediente>", f"<TextoExpediente>{expediente}</TextoExpediente>", x, flags=re.S)
            x = re.sub(r"<TituloSubGrupo>.*?</TituloSubGrupo>", "<TituloSubGrupo></TituloSubGrupo>", x, flags=re.S)
            x = re.sub(r"<TextoSubGrupo>.*?</TextoSubGrupo>", "<TextoSubGrupo></TextoSubGrupo>", x, flags=re.S)
            x = re.sub(r"<Asentimiento>\w+</Asentimiento>", f"<Asentimiento>{asent}</Asentimiento>", x)
            x = re.sub(r"<AFavor>\d+</AFavor>", f"<AFavor>{si}</AFavor>", x)
            x = re.sub(r"<EnContra>\d+</EnContra>", f"<EnContra>{no}</EnContra>", x)
            z.writestr(f"sesion999votacion{n}.xml", x.encode("iso-8859-1"))
    return str(destino)


def test_una_ley_organica_sin_mayoria_absoluta_sale_rechazada_y_el_asentimiento_aprobado(cli, tmp_path):
    zips = _zip_sintetico(tmp_path / "z", [
        ("Votación de conjunto del Proyecto de Ley Orgánica de prueba.", "No", 175, 170),
        ("Proposición no de Ley aprobada por asentimiento.", "Sí", 0, 0),
        ("Votación de conjunto de la Reforma del artículo 49 de la Constitución Española.", "No", 200, 100),
    ])
    cli("descargar", "--zips", zips)
    res = {v["numero"]: v["resultado"] for v in cli("exportar")["votaciones"]}
    assert res == {1: "rechazada", 2: "aprobada", 3: "rechazada"}


# --- Hallazgos 5, 6, 7 y 10: el juez ---

def _preparar(cli, zips, **env):
    cli("descargar", "--zips", zips)
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf"), env=_env(**env))
    cli("extraer", env=_env(**env))


def test_el_partido_de_un_cruce_es_siempre_el_dueno_de_la_promesa(cli, zips):
    _preparar(cli, zips)
    cli("juzgar", "--k", "3", env=_env(LLM_FALSO_PARTIDO="Vox"))   # los jueces dicen «Vox» para una promesa del PSOE
    datos = cli("exportar")
    duenos = {p["id"]: p["partido"] for p in datos["promesas"]}
    assert all(c["partido"] == duenos[c["promesa_id"]] for c in datos["cruces"])


def test_una_promesa_de_2026_nunca_se_cruza_con_votos_de_la_legislatura(cli, zips):
    _preparar(cli, zips)
    cli("ingest-programa", "2026", "Sumar", str(FIX / "programa_prueba.pdf"), env=_env())
    cli("extraer", env=_env())
    cli("juzgar", "--k", "6", env=_env(LLM_FALSO_TODOS="1"))
    datos = cli("exportar")
    anios = {p["id"]: p["anio"] for p in datos["promesas"]}
    assert datos["cruces"] and all(anios[c["promesa_id"]] == 2023 for c in datos["cruces"])


def test_si_un_partido_pasa_a_votar_dividido_su_veredicto_se_recalcula_al_exportar(cli, zips):
    import sqlite3
    _preparar(cli, zips)
    cli("juzgar", "--k", "3", env=_env())
    assert any(c["nivel"] == "veredicto" for c in cli("exportar")["cruces"])
    conn = sqlite3.connect(cli.db)
    conn.execute("UPDATE votos_partido SET dividido = 1 WHERE partido = 'PSOE'")   # p. ej., diputados.json corregido
    conn.commit(); conn.close()
    assert all(c["nivel"] == "juzga_tu" for c in cli("exportar")["cruces"] if c["partido"] == "PSOE")


def test_un_programa_cargado_despues_tambien_se_juzga(cli, zips):
    _preparar(cli, zips)
    cli("juzgar", "--k", "6", env=_env())
    cli("ingest-programa", "2023", "Sumar", str(FIX / "programa_prueba.pdf"), env=_env())
    cli("extraer", env=_env())
    salida = cli("juzgar", "--k", "6", env=_env(LLM_FALSO_TODOS="1"))
    assert not salida.startswith("0 expedientes")      # los candidatos cambiaron: se vuelve a juzgar
    assert any(c["partido"] == "Sumar" for c in cli("exportar")["cruces"])


def test_no_se_juzga_mientras_queden_bloques_sin_extraer(cli, zips):
    cli("descargar", "--zips", zips)
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf"), env=_env())
    cli("extraer", "--tope", "0", env=_env())          # nada extraído
    salida = cli("juzgar", "--k", "3", env=_env())
    assert "sin extraer" in salida
    cli("extraer", env=_env())
    cli("juzgar", "--k", "3", env=_env())
    assert cli("exportar")["cruces"]


def test_un_fallo_de_red_no_tumba_la_carga_ni_publica_nada_a_medias(cli, zips):
    import sqlite3
    _preparar(cli, zips)
    cli("juzgar", "--k", "3", env=_env(LLM_FALSO_EXCEPCION="1"))   # el CLI termina sin error
    assert cli("exportar")["cruces"] == []
    conn = sqlite3.connect(cli.db)
    assert conn.execute("SELECT COUNT(*) FROM gasto WHERE paso = 'juzgar'").fetchone()[0] == 1
    conn.close()
    cli("juzgar", "--k", "3", env=_env())
    assert cli("exportar")["cruces"]


# --- Hallazgo 8: página y cita de cada promesa ---

def test_una_promesa_de_la_segunda_pagina_enlaza_la_segunda_pagina(cli):
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_dos_paginas.pdf"), env=_env())
    cli("extraer", env=_env())
    lobbies = next(p for p in cli("exportar")["promesas"] if "lobbies" in p["texto"])
    assert lobbies["pagina"] == 2 and lobbies["url_programa_pagina"].endswith("#page=2")


def test_una_cita_que_no_esta_en_el_programa_no_se_publica(cli):
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_dos_paginas.pdf"), env=_env())
    cli("extraer", env=_env(LLM_FALSO_CITA_FALSA="1"))
    assert not [p for p in cli("exportar")["promesas"] if p["texto"] == "Promesa inventada"]


# --- Hallazgo 9: el enlace al BOCG no se adivina ---

def test_un_decreto_ley_no_enlaza_el_bocg_de_otro_decreto_con_numero_parecido(cli, zips, tmp_path):
    import json
    falsa = [{"OBJETO": "Real Decreto-ley 4/2026, de 3 de febrero, para la revalorización de las pensiones públicas y otras medidas urgentes en materia de Seguridad Social.",
              "ENLACESBOCG": "https://www.congreso.es/public_oficiales/L15/CONG/BOCG/D/BOCG-15-D-999-1.PDF#page=1"}]
    ini = tmp_path / "ini.json"
    ini.write_text(json.dumps(falsa, ensure_ascii=False), encoding="utf-8")
    cli("descargar", "--zips", zips)
    cli("fuentes", "--iniciativas", str(ini), "--boe", str(FIX / "boe_muestra.json"))
    v = next(v for v in cli("exportar")["votaciones"] if v["clave_iniciativa"] == "real decreto-ley 3/2026" and not v["excluida_tramite"])
    assert v["url_bocg"] is None


def test_una_enmienda_anunciada_en_el_titulo_es_votacion_parcial(cli, tmp_path):
    """El Congreso a veces no rellena el subgrupo y escribe «Votación de la enmienda.» al final del título."""
    zips = _zip_sintetico(tmp_path / "z", [
        ("Proposición de Ley de prueba sobre donantes.\nVotación de la enmienda.", "No", 150, 190),
        ("Proposición de Ley de prueba sobre donantes.", "No", 190, 150),
    ])
    cli("descargar", "--zips", zips)
    sub = {v["numero"]: v["subtipo"] for v in cli("exportar")["votaciones"]}
    assert sub == {1: "parcial", 2: "normal"}


def test_una_votacion_que_pasa_a_excluida_deja_de_publicar_sus_cruces(cli, tmp_path):
    """Si una corrección de datos reclasifica una votación como parcial, sus juicios anteriores no se publican."""
    ley = "Proposición de Ley sobre el alquiler de vivienda y de reforma de la Ley 29/1994 de Arrendamientos Urbanos."
    _preparar(cli, _zip_sintetico(tmp_path / "a", [(ley, "No", 190, 150)]), LLM_FALSO_TODOS="1")
    cli("juzgar", "--k", "3", env=_env(LLM_FALSO_TODOS="1"))
    assert cli("exportar")["cruces"], "sin cruces la prueba no mide nada"
    cli("descargar", "--zips", _zip_sintetico(tmp_path / "b", [(ley + "\nVotación de la enmienda.", "No", 190, 150)]))
    assert cli("exportar")["cruces"] == []
