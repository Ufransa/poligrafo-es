# src/electoral/votaciones.py
"""Votaciones del Pleno del Congreso (XV legislatura), voto a voto."""
import io
import json
import re
import time
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

import requests

from src.congreso import decode_vote_xml, compute_resultado

BASE = "https://www.congreso.es"
OPENDATA = BASE + "/es/opendata/votaciones"
PAGINA_DIA = (OPENDATA + "?p_p_id=votaciones&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view"
              "&targetLegislatura=XV&targetDate=")
CABECERAS = {"User-Agent": "PoligrafoES/1.0 (herramienta personal)"}
PAUSA = 1.5   # segundos entre peticiones: el Congreso es un servicio público, no un CDN

# Votaciones que no deciden el fondo de nada: solo cambian el procedimiento.
TRAMITE = re.compile(r"avocaci[oó]n|pr[oó]rroga|lectura [uú]nica|tramitaci[oó]n como proyecto de ley", re.I)

PREFIJOS = (
    "votación de la solicitud de avocación por el pleno de la cámara de la deliberación y votación final del ",
    "votación de la enmienda a la totalidad de devolución al ",
    "votación conjunta de las enmiendas a la totalidad de devolución al ",
    "votación de la enmienda a la totalidad de texto alternativo a la ",
    "votación de la enmienda a la totalidad de texto alternativo al ",
    "tramitación como proyecto de ley por el procedimiento de urgencia del ",
    "acuerdo de tramitación directa y en lectura única del ",
    "acuerdo de tramitación directa y en lectura única de la ",
    "votación del dictamen del ", "votación del dictamen de la ",
    "votación de conjunto del ", "votación de conjunto de la ",
)


def dias_con_votaciones(html: str) -> list[str]:
    """Fechas AAAAMMDD con votaciones según el calendario de la página de open data."""
    m = re.search(r"var diasVotaciones = \[([^\]]*)\]", html)
    return sorted(d.strip() for d in m.group(1).split(",")) if m else []


def urls_zip_del_dia(dia: str) -> list[str]:
    fecha = f"{dia[6:8]}/{dia[4:6]}/{dia[0:4]}"
    html = requests.get(PAGINA_DIA + fecha, headers=CABECERAS, timeout=30).text
    rutas = re.findall(r"/webpublica/opendata/votaciones/Leg15/Sesion\d+/" + dia + r"/VOT_[^\"']+\.zip", html)
    return [BASE + r for r in sorted(set(rutas))]


def descargar_legislatura(destino: Path, ya_bajados: set[str]) -> list[Path]:
    """Baja los ZIP que falten. Reanudable: no repite los de `ya_bajados` (nombres de archivo)."""
    destino.mkdir(parents=True, exist_ok=True)
    html = requests.get(OPENDATA, headers=CABECERAS, timeout=30).text
    nuevos = []
    for dia in dias_con_votaciones(html):
        for url in urls_zip_del_dia(dia):
            nombre = url.rsplit("/", 1)[1]
            if nombre in ya_bajados:
                continue
            r = requests.get(url, headers=CABECERAS, timeout=60)
            r.raise_for_status()
            (destino / nombre).write_bytes(r.content)
            nuevos.append(destino / nombre)
            time.sleep(PAUSA)
        time.sleep(PAUSA)
    return nuevos


def _fecha_iso(fecha_congreso: str) -> str:
    d, m, a = (int(x) for x in fecha_congreso.split("/"))
    return date(a, m, d).isoformat()


def leer_zip(ruta: Path) -> list[dict]:
    """Todas las votaciones de un ZIP de sesión, con el voto de cada diputado."""
    salida = []
    with zipfile.ZipFile(ruta) as zf:
        for nombre in zf.namelist():
            if not nombre.lower().endswith(".xml"):
                continue
            raiz = ET.fromstring(decode_vote_xml(zf.read(nombre)))
            info, tot = raiz.find("Informacion"), raiz.find("Totales")
            fecha = _fecha_iso(info.findtext("Fecha", "").strip())
            sesion = int(info.findtext("Sesion", 0))
            salida.append({
                "id": f"{sesion}-{int(info.findtext('NumeroVotacion', 0))}",
                "sesion": sesion,
                "numero": int(info.findtext("NumeroVotacion", 0)),
                "fecha": fecha,
                "tipo": info.findtext("Titulo", "").strip(),
                "expediente": info.findtext("TextoExpediente", "").strip(),
                "titulo_subgrupo": info.findtext("TituloSubGrupo", "").strip(),
                "texto_subgrupo": info.findtext("TextoSubGrupo", "").strip(),
                "a_favor": int(tot.findtext("AFavor", 0)),
                "en_contra": int(tot.findtext("EnContra", 0)),
                "abstenciones": int(tot.findtext("Abstenciones", 0)),
                "asentimiento": tot.findtext("Asentimiento", "").strip() == "Sí",
                "diputados": [
                    {"diputado": v.findtext("Diputado", "").strip(),
                     "grupo": v.findtext("Grupo", "").strip(),
                     "voto": v.findtext("Voto", "").strip()}
                    for v in raiz.findall(".//Votacion")
                ],
                "url_zip_nombre": ruta.name,
            })
    return salida


def clasificar(v: dict) -> tuple[str, bool]:
    """Subtipo de la votación y si es la convalidación de un decreto-ley."""
    texto = " ".join([v["tipo"], v["titulo_subgrupo"], v["texto_subgrupo"], v["expediente"]])
    if TRAMITE.search(texto):
        return "tramite", False
    bajo = texto.lower()
    if "texto alternativo" in bajo:
        return "texto_alternativo", False
    if "devoluci" in bajo:
        return "devolucion", False
    # Con subgrupo y sin ser totalidad es una votación parcial: una enmienda, un bloque de enmiendas o un
    # punto suelto. Su voto es táctica parlamentaria, no la postura sobre la iniciativa.
    if v["titulo_subgrupo"] and "totalidad" not in v["titulo_subgrupo"].lower():
        return "parcial", False
    # A veces el subgrupo viene vacío y la enmienda se anuncia al final del título.
    if re.search(r"votación de (la|las) enmiendas?\.?\s*$", v["expediente"].lower()):
        return "parcial", False
    es_conv = v["tipo"].lower().startswith("convalidación") and "real decreto-ley" in v["expediente"].lower()
    return "normal", es_conv


MAYORIA_ABSOLUTA = 176   # leyes orgánicas: votación de conjunto (art. 81 CE)
TRES_QUINTOS = 210       # reforma constitucional (art. 167 CE)


def resultado(v: dict) -> str:
    """Aprobada o rechazada según la mayoría que exige cada votación. El XML no trae el resultado."""
    if v.get("asentimiento"):
        return "aprobada"
    exp = v["expediente"].lower()
    if exp.startswith("votación de conjunto"):
        if "constitución" in exp and "reforma" in exp:
            return "aprobada" if v["a_favor"] >= TRES_QUINTOS else "rechazada"
        if "orgánica" in exp:
            return "aprobada" if v["a_favor"] >= MAYORIA_ABSOLUTA else "rechazada"
    return compute_resultado(v["a_favor"], v["en_contra"])


def clave_iniciativa(texto: str) -> str:
    """Identidad de la iniciativa, igual en todas sus votaciones (toma, totalidad, dictamen, conjunto)."""
    t = " ".join(texto.split()).lower()
    m = re.search(r"real decreto-ley \d+/\d{4}", t)
    if m:
        return m.group(0)
    for p in PREFIJOS:
        if t.startswith(p):
            t = t[len(p):]
            break
    return t.split(", presentada por")[0].split(". se vota")[0].strip(" .")


def votos_por_partido(v: dict, mapa: dict) -> dict:
    """{partido: {voto, dividido}}. El Mixto se reparte por diputado; los independientes no cuentan."""
    mixto = {}
    for p in mapa["mixto"]:
        mixto.setdefault(p["diputado"], []).append(p)
    por_partido: dict[str, Counter] = {}
    for d in v["diputados"]:
        if d["grupo"] == "GMx":
            tramos = [p for p in mixto.get(d["diputado"], []) if p["desde"] <= v["fecha"]]
            partido = tramos[-1]["partido"] if tramos else None
        else:
            partido = mapa["grupos"].get(d["grupo"])
        if partido is None or d["voto"] == "No vota":   # una ausencia no es un voto
            continue
        por_partido.setdefault(partido, Counter())[d["voto"]] += 1
    salida = {}
    for partido, c in por_partido.items():
        voto, n = c.most_common(1)[0]
        total = sum(c.values())
        salida[partido] = {"voto": voto, "dividido": (total - n) / total > 0.10}
    return salida


def url_sesion(fecha_iso: str) -> str:
    a, m, d = fecha_iso.split("-")
    return PAGINA_DIA + f"{d}/{m}/{a}"


def url_xml(nombre_zip: str, sesion: int, fecha_iso: str) -> str:
    return f"{BASE}/webpublica/opendata/votaciones/Leg15/Sesion{sesion:03d}/{fecha_iso.replace('-', '')}/{nombre_zip}"


def guardar(conn, v: dict, mapa: dict) -> None:
    subtipo, es_conv = clasificar(v)
    columnas = ("id", "fecha", "sesion", "numero", "tipo", "subtipo", "es_convalidacion", "expediente",
                "texto_subgrupo", "clave_iniciativa", "resultado", "a_favor", "en_contra", "abstenciones",
                "excluida_tramite", "url_xml", "url_sesion")
    # Upsert con columnas explícitas: volver a descargar no borra los enlaces que ya resolvió `fuentes`.
    conn.execute(
        f"INSERT INTO votaciones ({', '.join(columnas)}) VALUES ({', '.join('?' * len(columnas))}) "
        f"ON CONFLICT(id) DO UPDATE SET {', '.join(f'{c} = excluded.{c}' for c in columnas[1:])}",
        (v["id"], v["fecha"], v["sesion"], v["numero"], v["tipo"], subtipo, int(es_conv),
         v["expediente"], v["texto_subgrupo"], clave_iniciativa(v["expediente"]),
         resultado(v), v["a_favor"], v["en_contra"], v["abstenciones"],
         int(subtipo in ("tramite", "parcial")), url_xml(v["url_zip_nombre"], v["sesion"], v["fecha"]), url_sesion(v["fecha"])),
    )
    conn.execute("DELETE FROM votos_partido WHERE votacion_id = ?", (v["id"],))
    for partido, x in votos_por_partido(v, mapa).items():
        conn.execute("INSERT INTO votos_partido VALUES (?,?,?,?)", (v["id"], partido, x["voto"], int(x["dividido"])))


def cargar_mapa(raiz: Path) -> dict:
    return json.loads((raiz / "config" / "diputados.json").read_text(encoding="utf-8"))
