# electoral.py
"""Motor de datos de la web electoral del 29N. Ver docs/superpowers/specs/2026-10-07-web-electoral-29n-design.md."""
import argparse
import random
from pathlib import Path

from src.electoral import db as edb
import json

from src.electoral import exportar, fuentes, juez, noche, programas, votaciones
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
    try:
        print(juez.juzgar(conn, llm, k=a.k), "expedientes juzgados")
    finally:
        conn.execute("INSERT INTO gasto (fecha, paso, usd) VALUES (datetime('now'), 'juzgar', ?)", (llm.gastado,))
        conn.commit()
        print(f"gastado {llm.gastado:.4f} $")


def cmd_fuentes(a, conn):
    iniciativas = fuentes.indice_iniciativas(fuentes.cargar_iniciativas(a.iniciativas))
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


def cmd_muestra(a, conn):
    datos = exportar.construir(conn, RAIZ)
    prom = {p["id"]: p for p in datos["promesas"]}
    vots = {v["id"]: v for v in datos["votaciones"]}
    veredictos = [c for c in datos["cruces"] if c["nivel"] == "veredicto"]
    random.Random(a.semilla).shuffle(veredictos)
    L = ["# Muestra de veredictos para revisar antes de publicar", "",
         "Marca la casilla si estás de acuerdo. Si no, déjala vacía y escribe por qué en «Nota».", ""]
    for n, c in enumerate(veredictos[: a.n], 1):
        p, v = prom[c["promesa_id"]], vots[c["votacion_id"]]
        L += [f"## {n}. {c['partido']}: {c['veredicto'].upper()}", "",
              f"- **Se votó ({v['fecha']}):** {v['expediente'][:300]}",
              f"- **{c['partido']} votó:** {c['voto']}",
              f"- **Promesa:** {p['texto']}",
              f"- **Cita literal (pág. {p['pagina']}):** «{p['cita']}» ({p['url_programa_pagina']})", "",
              f"- [ ] De acuerdo con «{c['veredicto']}»", "- Nota: ", ""]
    Path(a.salida).write_text("\n".join(L), encoding="utf-8")
    print(f"{min(a.n, len(veredictos))} casos en {a.salida}")


def cmd_todo(a, conn):
    for paso, args in (("descargar", []), ("fuentes", []), ("extraer", ["--tope", str(a.tope_extraer)]),
                       ("juzgar", ["--tope", str(a.tope_juzgar)]), ("exportar", [])):
        print("==>", paso, flush=True)
        main([paso, *args, "--db", a.db])


def cmd_noche(a, conn):
    """Pasos del motor y, al final, aviso y publicación. La salud se escribe siempre, también si algo falla."""
    avisos, error = 0, None
    try:
        main(["descargar", *(["--zips", a.zips] if a.zips else []), "--db", a.db])
        main(["fuentes", *(["--iniciativas", a.iniciativas] if a.iniciativas else []),
              *(["--boe", a.boe] if a.boe else []), "--db", a.db])
        main(["juzgar", "--tope", str(a.tope), "--db", a.db])
        main(["exportar", "--salida", a.salida, "--db", a.db])
        datos = json.loads(Path(a.salida).read_text(encoding="utf-8"))
        avisos = noche.avisar(conn, datos)
        noche.publicar(Path(a.salida), Path(a.web))
    except Exception as e:                       # la salud lo cuenta y ARGUS avisa
        error = f"{type(e).__name__}: {getattr(e, 'stderr', '') or e}"[:500]
    noche.escribir_salud(Path(a.salud), error is None, avisos, error)
    if error:
        raise SystemExit(f"noche: {error}")


def cmd_exportar(a, conn):
    exportar.escribir(exportar.construir(conn, RAIZ, Path(a.revision) if a.revision else None), Path(a.salida))


def main(argv=None):
    p = argparse.ArgumentParser(prog="electoral")
    sub = p.add_subparsers(dest="cmd", required=True)
    for nombre in ("descargar", "fuentes", "ingest-programa", "extraer", "juzgar", "exportar", "muestra", "todo", "noche"):
        s = sub.add_parser(nombre)
        s.add_argument("--db", default=str(RAIZ / "electoral.db"))
    for arg in ("anio", "partido", "origen"):
        sub.choices["ingest-programa"].add_argument(arg)
    sub.choices["extraer"].add_argument("--tope", type=float, default=1.0)
    sub.choices["juzgar"].add_argument("--tope", type=float, default=4.0)
    sub.choices["juzgar"].add_argument("--k", type=int, default=20)
    sub.choices["fuentes"].add_argument("--iniciativas", help="JSON con iniciativas (por defecto, open data del Congreso)")
    sub.choices["muestra"].add_argument("--n", type=int, default=30)
    sub.choices["muestra"].add_argument("--semilla", type=int, default=29)
    sub.choices["muestra"].add_argument("--salida", default=str(RAIZ / "docs" / "revision_muestra.md"))
    sub.choices["todo"].add_argument("--tope-extraer", type=float, default=1.0)
    sub.choices["todo"].add_argument("--tope-juzgar", type=float, default=4.0)
    sub.choices["fuentes"].add_argument("--boe", help="JSON clave -> identificador BOE (por defecto, API del BOE)")
    sub.choices["descargar"].add_argument("--zips", help="carpeta con ZIPs ya bajados (no descarga nada)")
    sub.choices["exportar"].add_argument("--salida", default=str(RAIZ / "datos.json"))
    sub.choices["noche"].add_argument("--web", required=True, help="clon local de poligrafo-web")
    sub.choices["noche"].add_argument("--zips", help="carpeta con ZIPs ya bajados (pruebas)")
    sub.choices["noche"].add_argument("--iniciativas")
    sub.choices["noche"].add_argument("--boe")
    sub.choices["noche"].add_argument("--tope", type=float, default=0.3)
    sub.choices["noche"].add_argument("--salida", default=str(RAIZ / "datos.json"))
    sub.choices["noche"].add_argument("--salud", default=str(RAIZ / "electoral_data" / "noche.json"))
    sub.choices["exportar"].add_argument("--revision", help="JSON con los cruces confirmados a mano (por defecto, config/revision_manual.json)")
    a = p.parse_args(argv)
    conn = edb.conectar(Path(a.db))
    {"descargar": cmd_descargar, "ingest-programa": cmd_ingest, "extraer": cmd_extraer, "juzgar": cmd_juzgar, "fuentes": cmd_fuentes, "muestra": cmd_muestra, "todo": cmd_todo,
     "exportar": cmd_exportar, "noche": cmd_noche}[a.cmd](a, conn)


if __name__ == "__main__":
    main()
