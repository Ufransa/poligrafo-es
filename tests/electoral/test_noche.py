"""La ejecución nocturna: votaciones nuevas → juicio → datos.json → aviso de «incumple» → push a la web."""
import json
import os
import subprocess
import sys
from pathlib import Path

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "electoral"
RAIZ = Path(__file__).resolve().parents[2]


def _git(*a, cwd):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, encoding="utf-8", check=True).stdout


def _web(tmp_path):
    """Un remoto desnudo y su clon: hace de poligrafo-web."""
    remoto = tmp_path / "remoto.git"
    _git("init", "--bare", "-b", "main", str(remoto), cwd=tmp_path)
    clon = tmp_path / "web"
    _git("clone", str(remoto), str(clon), cwd=tmp_path)
    _git("config", "user.email", "t@t", cwd=clon)
    _git("config", "user.name", "t", cwd=clon)
    (clon / "README.md").write_text("web", encoding="utf-8")
    _git("add", "-A", cwd=clon)
    _git("commit", "-m", "inicio", cwd=clon)
    _git("push", "origin", "main", cwd=clon)
    return remoto, clon


def _noche(tmp_path, zips, web, avisos, **env):
    entorno = {**os.environ, "ELECTORAL_LLM_FALSO": str(FIX / "llm_falso.py"), "LLM_FALSO_TODOS": "1",
               "ELECTORAL_AVISOS_FALSO": str(avisos), **env}
    db = tmp_path / "electoral.db"
    if not db.exists():
        for args in (["ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf")], ["extraer"]):
            subprocess.run([sys.executable, str(RAIZ / "electoral.py"), *args, "--db", str(db)], cwd=RAIZ, env=entorno, check=True)
    return subprocess.run([sys.executable, str(RAIZ / "electoral.py"), "noche", "--zips", zips, "--web", str(web),
                           "--iniciativas", str(FIX / "iniciativas_muestra.json"), "--boe", str(FIX / "boe_muestra.json"),
                           "--salida", str(tmp_path / "datos.json"), "--salud", str(tmp_path / "noche.json"), "--db", str(db)],
                          cwd=RAIZ, env=entorno, capture_output=True, text=True, encoding="utf-8")


def test_la_noche_publica_datos_json_en_la_web(tmp_path, zips):
    remoto, clon = _web(tmp_path)
    r = _noche(tmp_path, zips, clon, tmp_path / "avisos.jsonl")
    assert r.returncode == 0, r.stderr
    publicado = json.loads(_git("show", "main:data/datos.json", cwd=remoto))
    assert publicado["meta"]["version_contrato"].startswith("1.")
    salud = json.loads((tmp_path / "noche.json").read_text(encoding="utf-8"))
    assert salud["publicado"] is True and salud["error"] is None


def test_un_incumple_nuevo_se_avisa_una_sola_vez(tmp_path, zips):
    _, clon = _web(tmp_path)
    avisos = tmp_path / "avisos.jsonl"
    _noche(tmp_path, zips, clon, avisos, LLM_FALSO_POSTURA="en_contra")
    primera = avisos.read_text(encoding="utf-8").splitlines()
    assert primera, "con promesas en contra y votos Sí tiene que haber «incumple» por revisar"
    assert all("Revisar" in json.loads(x)["texto"] for x in primera)
    _noche(tmp_path, zips, clon, avisos, LLM_FALSO_POSTURA="en_contra")
    assert avisos.read_text(encoding="utf-8").splitlines() == primera


def test_si_el_push_falla_la_salud_lo_dice_y_sale_con_error(tmp_path, zips):
    remoto, clon = _web(tmp_path)
    _git("remote", "set-url", "origin", str(tmp_path / "no-existe.git"), cwd=clon)
    r = _noche(tmp_path, zips, clon, tmp_path / "avisos.jsonl")
    assert r.returncode != 0
    salud = json.loads((tmp_path / "noche.json").read_text(encoding="utf-8"))
    assert salud["publicado"] is False and salud["error"]


def test_un_incumple_por_revisar_va_marcado_en_el_contrato(cli, zips):
    entorno = {**os.environ, "ELECTORAL_LLM_FALSO": str(FIX / "llm_falso.py"), "LLM_FALSO_TODOS": "1",
               "LLM_FALSO_POSTURA": "en_contra"}
    cli("descargar", "--zips", zips)
    cli("ingest-programa", "2023", "PSOE", str(FIX / "programa_prueba.pdf"), env=entorno)
    cli("extraer", env=entorno)
    cli("juzgar", "--k", "3", env=entorno)
    cruces = cli("exportar")["cruces"]
    pendientes = [c for c in cruces if c["pendiente_revision"]]
    assert pendientes and all(c["nivel"] == "juzga_tu" and c["veredicto"] == "incumple" for c in pendientes)
    assert all(not c["pendiente_revision"] for c in cruces if c["veredicto"] == "cumple")


def test_si_la_web_recibe_cambios_de_codigo_la_noche_sigue_publicando(tmp_path, zips):
    """Un push de código a poligrafo-web desde el PC deja atrás el clon de la Pi: no puede bloquear la publicación."""
    remoto, clon = _web(tmp_path)
    otro = tmp_path / "pc"
    _git("clone", str(remoto), str(otro), cwd=tmp_path)
    _git("config", "user.email", "t@t", cwd=otro)
    _git("config", "user.name", "t", cwd=otro)
    (otro / "README.md").write_text("web con cambios", encoding="utf-8")
    _git("commit", "-am", "cambio de codigo", cwd=otro)
    _git("push", "origin", "main", cwd=otro)
    r = _noche(tmp_path, zips, clon, tmp_path / "avisos.jsonl")
    assert r.returncode == 0, r.stderr
    assert _git("show", "main:README.md", cwd=remoto) == "web con cambios"
    assert json.loads(_git("show", "main:data/datos.json", cwd=remoto))["meta"]
