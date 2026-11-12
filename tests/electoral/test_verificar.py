"""El paso `verificar`: segunda pasada sobre los veredictos firmes con el texto de la iniciativa (BOCG).

Qué entra y qué sale: entra un cruce que el juez dio por firme viendo solo el título; sale igual, o baja a
«Juzga tú» si el texto de la iniciativa decide otra cosa. Nunca sube un cruce, nunca cambia su sentido, y sin
texto del BOCG no decide.
"""
import json
import os
import sqlite3
from pathlib import Path

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "electoral"
INICIATIVAS = str(FIX / "iniciativas_muestra.json")
TEXTO = ("Exposición de motivos. La presente ley regula la transparencia de las actividades de los grupos de interés "
         "y crea un registro público. " * 8 + "Artículo 1. Objeto de la ley. Artículo 2. Registro de grupos de interés.")


def _env(**extra):
    return {**os.environ, "ELECTORAL_LLM_FALSO": str(FIX / "llm_falso.py"), **extra}


def _preparar(cli, zips, tmp_path, con_texto=True):
    """Deja la base con veredictos firmes, unos con BOCG y otros sin él, y devuelve el entorno para `verificar`."""
    cli("descargar", "--zips", zips)
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf"), env=_env())
    cli("extraer", env=_env())
    cli("fuentes", "--iniciativas", INICIATIVAS, "--boe", str(FIX / "boe_muestra.json"))
    cli("juzgar", "--k", "3", env=_env())
    urls = {v["url_bocg"] for v in cli("exportar")["votaciones"] if v["url_bocg"]}
    bocg = tmp_path / "bocg.json"
    bocg.write_text(json.dumps({u: TEXTO for u in urls} if con_texto else {}), encoding="utf-8")
    return {"ELECTORAL_BOCG_FALSO": str(bocg)}


def _firmes(datos):
    return {(c["votacion_id"], c["promesa_id"], c["veredicto"]) for c in datos["cruces"] if c["nivel"] == "veredicto"}


def _con_bocg(datos):
    return {v["id"] for v in datos["votaciones"] if v["url_bocg"]}


def _gasto(cli):
    conn = sqlite3.connect(cli.db)
    try:
        return conn.execute("SELECT COALESCE(SUM(usd), 0) FROM gasto WHERE paso = 'verificar'").fetchone()[0]
    finally:
        conn.close()


def test_a_firm_verdict_drops_to_juzga_tu_when_the_initiative_text_decides_something_else(cli, zips, tmp_path):
    bocg = _preparar(cli, zips, tmp_path)
    antes = cli("exportar")
    con_texto = {f for f in _firmes(antes) if f[0] in _con_bocg(antes)}
    assert con_texto, "el fixture debe dar algún veredicto firme con BOCG"
    cli("verificar", "--iniciativas", INICIATIVAS, env=_env(LLM_FALSO_VERIFICA="otro", **bocg))
    despues = cli("exportar")
    assert not con_texto & _firmes(despues)
    bajados = {(c["votacion_id"], c["promesa_id"]): c for c in despues["cruces"]}
    for vid, pid, veredicto in con_texto:           # sigue publicado, en «Juzga tú» y con el mismo sentido
        assert (bajados[(vid, pid)]["nivel"], bajados[(vid, pid)]["veredicto"]) == ("juzga_tu", veredicto)


def test_a_firm_verdict_stays_when_the_text_decides_what_was_promised(cli, zips, tmp_path):
    bocg = _preparar(cli, zips, tmp_path)
    antes = cli("exportar")
    cli("verificar", "--iniciativas", INICIATIVAS, env=_env(LLM_FALSO_VERIFICA="mismo", **bocg))
    assert cli("exportar")["cruces"] == antes["cruces"]


def test_when_the_model_is_unsure_the_verdict_stays(cli, zips, tmp_path):
    bocg = _preparar(cli, zips, tmp_path)
    antes = cli("exportar")
    cli("verificar", "--iniciativas", INICIATIVAS, env=_env(LLM_FALSO_VERIFICA="no_se", **bocg))
    assert cli("exportar")["cruces"] == antes["cruces"]


def test_without_bocg_text_the_step_does_not_decide_and_costs_nothing(cli, zips, tmp_path):
    bocg = _preparar(cli, zips, tmp_path, con_texto=False)
    antes = cli("exportar")
    cli("verificar", "--iniciativas", INICIATIVAS, env=_env(LLM_FALSO_VERIFICA="otro", **bocg))
    assert cli("exportar")["cruces"] == antes["cruces"]
    assert _gasto(cli) == 0


def test_verdicts_without_a_bocg_link_are_never_touched(cli, zips, tmp_path):
    bocg = _preparar(cli, zips, tmp_path)
    antes = cli("exportar")
    sin_texto = {f for f in _firmes(antes) if f[0] not in _con_bocg(antes)}
    cli("verificar", "--iniciativas", INICIATIVAS, env=_env(LLM_FALSO_VERIFICA="otro", **bocg))
    assert sin_texto <= _firmes(cli("exportar"))


def test_the_step_never_promotes_or_flips_a_cruce(cli, zips, tmp_path):
    bocg = _preparar(cli, zips, tmp_path)
    antes = {(c["votacion_id"], c["promesa_id"]): c for c in cli("exportar")["cruces"]}
    cli("verificar", "--iniciativas", INICIATIVAS, env=_env(LLM_FALSO_VERIFICA="otro", LLM_FALSO_VERIFICA_MEZCLA="1", **bocg))
    despues = {(c["votacion_id"], c["promesa_id"]): c for c in cli("exportar")["cruces"]}
    assert set(despues) == set(antes)                                   # no quita ni añade cruces
    for k, c in despues.items():
        assert c["veredicto"] == antes[k]["veredicto"]                    # nunca cambia el sentido
        assert not (c["nivel"] == "veredicto" and antes[k]["nivel"] != "veredicto")   # nunca sube


def test_it_does_not_rejudge_anything(cli, zips, tmp_path):
    bocg = _preparar(cli, zips, tmp_path)
    conn = sqlite3.connect(cli.db)
    juicios = conn.execute("SELECT votacion_id, respuestas, candidatos FROM juicios ORDER BY 1").fetchall()
    gasto_juez = conn.execute("SELECT SUM(usd) FROM gasto WHERE paso = 'juzgar'").fetchone()[0]
    conn.close()
    cli("verificar", "--iniciativas", INICIATIVAS, env=_env(LLM_FALSO_VERIFICA="otro", **bocg))
    cli("juzgar", "--k", "3", env=_env())                                # el juez no tiene nada nuevo que hacer
    conn = sqlite3.connect(cli.db)
    assert conn.execute("SELECT votacion_id, respuestas, candidatos FROM juicios ORDER BY 1").fetchall() == juicios
    assert conn.execute("SELECT SUM(usd) FROM gasto WHERE paso = 'juzgar'").fetchone()[0] == gasto_juez
    conn.close()


def test_running_it_twice_costs_nothing_the_second_time(cli, zips, tmp_path):
    bocg = _preparar(cli, zips, tmp_path)
    cli("verificar", "--iniciativas", INICIATIVAS, env=_env(**bocg))
    primero = _gasto(cli)
    assert primero > 0
    cli("verificar", "--iniciativas", INICIATIVAS, env=_env(**bocg))
    assert _gasto(cli) == primero


def test_if_the_budget_runs_out_it_stops_and_resumes_later(cli, zips, tmp_path):
    bocg = _preparar(cli, zips, tmp_path)
    antes = cli("exportar")
    con_texto = {f for f in _firmes(antes) if f[0] in _con_bocg(antes)}
    cli("verificar", "--iniciativas", INICIATIVAS, "--tope", "0.001", env=_env(LLM_FALSO_VERIFICA="otro", LLM_FALSO_COSTE="0.001", **bocg))
    cli("exportar")                                                       # lo que quedó a medias no rompe la exportación
    cli("verificar", "--iniciativas", INICIATIVAS, env=_env(LLM_FALSO_VERIFICA="otro", **bocg))
    assert not con_texto & _firmes(cli("exportar"))


def test_a_model_failure_leaves_the_verdict_as_it_was(cli, zips, tmp_path):
    bocg = _preparar(cli, zips, tmp_path)
    antes = cli("exportar")
    cli("verificar", "--iniciativas", INICIATIVAS, env=_env(LLM_FALSO_VERIFICA="falla", **bocg))
    assert cli("exportar")["cruces"] == antes["cruces"]


def _forzar_incumple(cli):
    """Un «incumple» unánime con BOCG: el partido votó lo contrario de lo que el juez dice que prometió."""
    datos = cli("exportar")
    vid, pid = next((c["votacion_id"], c["promesa_id"]) for c in datos["cruces"]
                    if c["nivel"] == "veredicto" and c["votacion_id"] in _con_bocg(datos))
    conn = sqlite3.connect(cli.db)
    actual = conn.execute("SELECT voto FROM votos_partido WHERE votacion_id = ? AND partido = 'PSOE'", (vid,)).fetchone()[0]
    conn.execute("UPDATE votos_partido SET voto = ? WHERE votacion_id = ? AND partido = 'PSOE'",
                 ("No" if actual == "Sí" else "Sí", vid))
    conn.commit(); conn.close()
    return vid, pid


def _cruce(datos, vid, pid):
    return next(c for c in datos["cruces"] if (c["votacion_id"], c["promesa_id"]) == (vid, pid))


def test_an_incumple_is_never_lowered_by_the_step(cli, zips, tmp_path):
    # Un «incumple» ya solo es firme si una persona lo confirma; el modelo no decide sobre él (2026-11-12:
    # la regla de mezcla ocultó el aviso de un «incumple» correcto).
    bocg = _preparar(cli, zips, tmp_path)
    vid, pid = _forzar_incumple(cli)
    for env in ({"LLM_FALSO_VERIFICA": "otro"}, {"LLM_FALSO_VERIFICA": "mismo", "LLM_FALSO_VERIFICA_MEZCLA": "1"}):
        cli("verificar", "--iniciativas", INICIATIVAS, env=_env(**env, **bocg))
        c = _cruce(cli("exportar"), vid, pid)
        assert (c["veredicto"], c["pendiente_revision"]) == ("incumple", True)


def test_an_incumple_confirmed_by_hand_stays_firm_even_if_the_step_disagrees(cli, zips, tmp_path):
    bocg = _preparar(cli, zips, tmp_path)
    vid, pid = _forzar_incumple(cli)
    revision = tmp_path / "revision.json"
    revision.write_text(json.dumps({"confirmados": [{"votacion_id": vid, "promesa_id": pid, "partido": "PSOE", "veredicto": "incumple"}]}),
                        encoding="utf-8")
    cli("verificar", "--iniciativas", INICIATIVAS, env=_env(LLM_FALSO_VERIFICA="otro", **bocg))
    c = _cruce(cli("exportar", "--revision", str(revision)), vid, pid)
    assert (c["nivel"], c["veredicto"], c["revisado_a_mano"]) == ("veredicto", "incumple", True)


def test_a_cumple_on_a_law_that_mixes_matters_stays_firm(cli, zips, tmp_path):
    bocg = _preparar(cli, zips, tmp_path)
    antes = cli("exportar")
    cumple = {f for f in _firmes(antes) if f[2] == "cumple"}
    cli("verificar", "--iniciativas", INICIATIVAS, env=_env(LLM_FALSO_VERIFICA="mismo", LLM_FALSO_VERIFICA_MEZCLA="1", **bocg))
    assert cumple <= _firmes(cli("exportar"))
