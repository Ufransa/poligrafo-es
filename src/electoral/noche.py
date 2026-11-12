"""Ejecución nocturna en la Orange Pi: avisa de los «incumple» por revisar y publica datos.json en poligrafo-web."""
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _enviar(texto: str) -> None:
    falso = os.environ.get("ELECTORAL_AVISOS_FALSO")
    if falso:
        with open(falso, "a", encoding="utf-8") as f:
            f.write(json.dumps({"texto": texto}, ensure_ascii=False) + "\n")
        return
    from dotenv import load_dotenv
    from src.publisher import send_message
    load_dotenv()
    send_message(os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHANNEL_ID"], texto)


COMPROBAR = ("Antes de confirmar, abre la iniciativa y comprueba (el título no basta):\n"
             "1. ¿Decide lo mismo que promete el programa, o solo toca la misma ley o el mismo tema?\n"
             "2. ¿Mete otros asuntos que expliquen el voto?\n"
             "3. En el Diario de Sesiones, ¿por qué dijo el partido que votaba así?\n"
             "Si dudas en cualquiera, no lo confirmes: queda en «Juzga tú».")


def mensaje_revision(c: dict, p: dict, v: dict, confirmar: dict, nota_texto: str | None = None) -> str:
    """El aviso lleva el texto de la iniciativa y la sesión: confirmar solo con el título repetía el error del
    juez (revisión del 2026-11-11: 4 de los 6 «incumple» confirmados no se sostenían al leer la iniciativa)."""
    enlaces = [f"Iniciativa (BOCG): {v.get('url_bocg') or 'sin enlace, búscala por el título'}",
               f"Sesión y Diario de Sesiones: {v.get('url_sesion') or '-'}"]
    if v.get("url_boe"):
        enlaces.append(f"BOE: {v['url_boe']}")
    nota = f"\n⚠️ {v['mezcla']['motivo']}" if v.get("mezcla") else ""
    if nota_texto:                           # paso `verificar`: lo que el modelo vio en el texto del BOCG
        nota += f"\n🔎 {nota_texto}"
    return (f"<b>Revisar «incumple»: {c['partido']}</b>\n{v['fecha']} · {v.get('tipo', '')}\n"
            f"{v['expediente'][:300]}{nota}\n"
            f"Votó {c['voto']}. Promesa: {p['texto']}\n«{p['cita']}» ({p['url_programa_pagina']})\n\n"
            + "\n".join(enlaces) + f"\n\n{COMPROBAR}\n\n"
            f"Para confirmarlo: añadir {json.dumps(confirmar, ensure_ascii=False)} a «confirmados» en "
            f"config/revision_manual.json. Si no es comparable, a «descartados» con un «motivo».")


def avisar(conn, datos: dict) -> int:
    """Un mensaje por cada «incumple» unánime que aún no está revisado ni avisado."""
    prom = {p["id"]: p for p in datos["promesas"]}
    vots = {v["id"]: v for v in datos["votaciones"]}
    hechos = {(r[0], r[1], r[2]) for r in conn.execute("SELECT votacion_id, promesa_id, partido FROM avisos")}
    from src.electoral import verificar
    notas = verificar.notas(conn)
    n = 0
    for c in datos["cruces"]:
        clave = (c["votacion_id"], c["promesa_id"], c["partido"])
        if not c["pendiente_revision"] or clave in hechos:
            continue
        p, v = prom[c["promesa_id"]], vots[c["votacion_id"]]
        confirmar = dict(zip(("votacion_id", "promesa_id", "partido"), clave)) | {"veredicto": "incumple"}
        _enviar(mensaje_revision(c, p, v, confirmar, notas.get(clave)))
        conn.execute("INSERT INTO avisos VALUES (?,?,?, datetime('now'))", clave)
        conn.commit()
        n += 1
    return n


def publicar(datos_json: Path, web: Path) -> None:
    """Copia datos.json al clon de poligrafo-web y hace push. Nunca fuerza: si no puede integrar el remoto, falla."""
    def git(*a):
        return subprocess.run(["git", *a], cwd=web, capture_output=True, text=True, check=True)

    # Los cambios de código de la web se suben desde el PC: el clon de la Pi los trae antes de publicar.
    git("pull", "--rebase", "origin", "HEAD")
    destino = web / "data" / "datos.json"
    destino.parent.mkdir(exist_ok=True)
    shutil.copyfile(datos_json, destino)
    git("add", "data/datos.json")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=web).returncode != 0:
        git("commit", "-m", f"datos: {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")
    git("push", "origin", "HEAD")


def escribir_salud(ruta: Path, publicado: bool, avisos: int, error: str | None, aviso: str | None = None) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps({"written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                "publicado": publicado, "avisos": avisos, "error": error,
                                "aviso": aviso}, ensure_ascii=False),
                    encoding="utf-8")
