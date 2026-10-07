# electoral.py
"""Motor de datos de la web electoral del 29N. Ver docs/superpowers/specs/2026-10-07-web-electoral-29n-design.md."""
import argparse
from pathlib import Path

from src.electoral import db as edb
import json

from src.electoral import exportar, fuentes, juez, programas, votaciones
from src.electoral.llm import LLM

RAIZ = Path(__file__).resolve().parent


def cmd_descargar(a, conn):
    destino = Path(a.zips) if a.zips else RAIZ / "electoral_data" / "zips"
    if not a.zips:
        hechos = {r["nombre"] for r in conn.execute("SELECT nombre FROM zips")}
        votaciones.descargar_legislatura(destino, hechos)
    mapa = votaciones.cargar_mapa(RAIZ)
    for ruta in sorted(destino.glob("*.zip")):
        for v in votaciones.leer_zip(ruta):
            votaciones.guardar(conn, v, mapa)
        conn.execute("INSERT OR IGNORE INTO zips VALUES (?,?,?)", (ruta.name, "", ""))
    conn.commit()


def cmd_ingest(a, conn):
    print(programas.ingerir(conn, int(a.anio), a.partido, a.origen), "bloques nuevos")


def cmd_extraer(a, conn):
    llm = LLM(a.tope)
    programas.extraer(conn, llm)
    conn.execute("INSERT INTO gasto (fecha, paso, usd) VALUES (datetime('now'), 'extraer', ?)", (llm.gastado,))
    conn.commit()
    print(f"gastado {llm.gastado:.4f} $")


def cmd_juzgar(a, conn):
    llm = LLM(a.tope)
    juez.juzgar(conn, llm, k=a.k)
    conn.execute("INSERT INTO gasto (fecha, paso, usd) VALUES (datetime('now'), 'juzgar', ?)", (llm.gastado,))
    conn.commit()
    print(f"gastado {llm.gastado:.4f} $")


def cmd_fuentes(a, conn):
    iniciativas = fuentes.cargar_iniciativas(a.iniciativas)
    vs = conn.execute("SELECT * FROM votaciones WHERE excluida_tramite = 0").fetchall()
    if a.boe:
        boe = json.loads(Path(a.boe).read_text(encoding="utf-8"))
    else:
        boe = {r["clave"]: r["identificador"] for r in conn.execute("SELECT * FROM boe")}
        for v in vs:
            if fuentes.es_final_aprobada(v) and v["clave_iniciativa"] not in boe:
                boe[v["clave_iniciativa"]] = fuentes.resolver_boe(v["clave_iniciativa"])
                conn.execute("INSERT OR REPLACE INTO boe VALUES (?, ?)", (v["clave_iniciativa"], boe[v["clave_iniciativa"]]))
    for v in vs:
        conn.execute("UPDATE votaciones SET url_bocg = ?, url_boe = ? WHERE id = ?",
                     (fuentes.url_bocg(v["expediente"], iniciativas), fuentes.url_boe(v, boe), v["id"]))
    conn.commit()


def cmd_exportar(a, conn):
    exportar.escribir(exportar.construir(conn, RAIZ), Path(a.salida))


def main():
    p = argparse.ArgumentParser(prog="electoral")
    sub = p.add_subparsers(dest="cmd", required=True)
    for nombre in ("descargar", "fuentes", "ingest-programa", "extraer", "juzgar", "exportar"):
        s = sub.add_parser(nombre)
        s.add_argument("--db", default=str(RAIZ / "electoral.db"))
    for arg in ("anio", "partido", "origen"):
        sub.choices["ingest-programa"].add_argument(arg)
    sub.choices["extraer"].add_argument("--tope", type=float, default=1.0)
    sub.choices["juzgar"].add_argument("--tope", type=float, default=4.0)
    sub.choices["juzgar"].add_argument("--k", type=int, default=20)
    sub.choices["fuentes"].add_argument("--iniciativas", help="JSON con iniciativas (por defecto, open data del Congreso)")
    sub.choices["fuentes"].add_argument("--boe", help="JSON clave -> identificador BOE (por defecto, API del BOE)")
    sub.choices["descargar"].add_argument("--zips", help="carpeta con ZIPs ya bajados (no descarga nada)")
    sub.choices["exportar"].add_argument("--salida", default=str(RAIZ / "datos.json"))
    a = p.parse_args()
    conn = edb.conectar(Path(a.db))
    {"descargar": cmd_descargar, "ingest-programa": cmd_ingest, "extraer": cmd_extraer, "juzgar": cmd_juzgar, "fuentes": cmd_fuentes,
     "exportar": cmd_exportar}[a.cmd](a, conn)


if __name__ == "__main__":
    main()
