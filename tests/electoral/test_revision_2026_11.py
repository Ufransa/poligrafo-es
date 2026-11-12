"""Lo que la web publica (y lo que no) tras la revisión de los veredictos del 2026-11-11.

Esa revisión leyó el contenido real de las iniciativas: 4 de los 6 «incumple» confirmados a mano no se
sostenían, 190 de los 298 «incumple» de «Juzga tú» eran mociones o PNL de título genérico sin relación
directa, y 13 tenían la postura leída al revés. Estas pruebas fijan las reglas que lo evitan.
"""
import json

from src.electoral import db, exportar, juez, noche, programas, votaciones

DIRECTA = {"postura": "en_contra", "fuerza": "directa"}
INDIRECTA = {"postura": "en_contra", "fuerza": "indirecta"}


def _base(tmp_path):
    return db.conectar(tmp_path / "e.db")


def _votacion(conn, vid, expediente, voto, partido="PP", tipo="Proposiciones no de Ley.", subtipo="normal"):
    conn.execute("INSERT INTO votaciones (id, fecha, tipo, subtipo, expediente, excluida_tramite) "
                 "VALUES (?, '2025-01-01', ?, ?, ?, 0)", (vid, tipo, subtipo, expediente))
    conn.execute("INSERT INTO votos_partido VALUES (?, ?, ?, 0)", (vid, partido, voto))


def _cruce(conn, vid, jueces, promesa_id=1, partido="PP"):
    conn.execute("INSERT INTO cruces VALUES (?, ?, ?, '', '', ?)",
                 (vid, promesa_id, partido, json.dumps(dict(zip(juez.JUECES, jueces)))))


def _publicados(conn, confirmados=frozenset(), descartados=frozenset()):
    return {(c["votacion_id"], c["nivel"], c["veredicto"])
            for c in exportar._cruces(conn, set(confirmados), set(descartados))}


# --- «Juzga tú» ------------------------------------------------------------------

def test_an_incumple_with_no_judge_seeing_a_direct_link_is_not_published(tmp_path):
    conn = _base(tmp_path)
    _votacion(conn, "1-1", "Moción del Grupo Parlamentario Socialista, sobre política de vivienda.", "Sí")
    _cruce(conn, "1-1", [INDIRECTA, INDIRECTA, None])
    assert _publicados(conn) == set()


def test_an_incumple_with_one_direct_judge_stays_in_juzga_tu(tmp_path):
    conn = _base(tmp_path)
    _votacion(conn, "1-1", "Moción del Grupo Parlamentario Socialista, sobre política de vivienda.", "Sí")
    _cruce(conn, "1-1", [DIRECTA, INDIRECTA, None])
    assert _publicados(conn) == {("1-1", "juzga_tu", "incumple")}


def test_a_cumple_without_direct_judges_is_still_published_in_juzga_tu(tmp_path):
    conn = _base(tmp_path)
    _votacion(conn, "1-1", "Moción del Grupo Parlamentario Socialista, sobre política de vivienda.", "No")
    _cruce(conn, "1-1", [INDIRECTA, INDIRECTA, None])
    assert _publicados(conn) == {("1-1", "juzga_tu", "cumple")}


# --- postura leída al revés --------------------------------------------------------

def test_voting_yes_to_your_own_initiative_never_shows_as_incumple(tmp_path):
    # PP vota «Sí» a su propia PNL contra el cierre nuclear; el juez leyó la promesa «en contra» por el título
    conn = _base(tmp_path)
    _votacion(conn, "91-1", "Proposición no de Ley presentada por el Grupo Parlamentario Popular en el Congreso, "
                            "sobre el cierre de las centrales nucleares.", "Sí")
    _cruce(conn, "91-1", [DIRECTA, DIRECTA, DIRECTA])
    assert _publicados(conn) == set()


def test_another_groups_initiative_can_still_be_an_incumple(tmp_path):
    conn = _base(tmp_path)
    _votacion(conn, "91-1", "Proposición no de Ley presentada por el Grupo Parlamentario VOX, "
                            "sobre el cierre de las centrales nucleares.", "Sí")
    _cruce(conn, "91-1", [DIRECTA, DIRECTA, DIRECTA])
    assert _publicados(conn) == {("91-1", "juzga_tu", "incumple")}


def test_your_own_return_amendment_can_still_be_an_incumple(tmp_path):
    # La devolución invierte el voto: votar «Sí» a tu enmienda de devolución es votar contra el proyecto
    conn = _base(tmp_path)
    _votacion(conn, "5-1", "Enmienda de totalidad de devolución presentada por el Grupo Parlamentario Popular en "
                           "el Congreso al Proyecto de Ley de Salud Pública.", "Sí", subtipo="devolucion",
              tipo="Debates de totalidad de iniciativas legislativas.")
    _cruce(conn, "5-1", [{"postura": "a_favor", "fuerza": "directa"}] * 3)
    assert _publicados(conn) == {("5-1", "juzga_tu", "incumple")}


def test_authors_are_read_from_every_title_format():
    assert votaciones.autores("Proposición no de Ley presentada por el Grupo Parlamentario VOX, sobre el lobo.") == {"Vox"}
    assert votaciones.autores("Proposición de Ley de los Grupos Parlamentarios Popular en el Congreso y "
                              "Socialista, Orgánica de reforma de la LOPJ.") == {"PP", "PSOE"}
    assert votaciones.autores("Moción consecuencia de interpelación urgente del Grupo Parlamentario Popular en el "
                              "Congreso, sobre vivienda.") == {"PP"}
    assert votaciones.autores("Proposición de Ley del Grupo Parlamentario Vasco (EAJ-PNV), de secretos oficiales.") == {"PNV"}
    assert votaciones.autores("Proyecto de Ley de movilidad sostenible.") == set()


# --- revisión manual ---------------------------------------------------------------

def test_a_discarded_cross_disappears_from_the_web(tmp_path):
    conn = _base(tmp_path)
    _votacion(conn, "57-1", "Proposición de Ley del Grupo Parlamentario Popular en el Congreso, Orgánica de "
                            "modificación de la LOREG.", "No")
    _cruce(conn, "57-1", [DIRECTA, DIRECTA, DIRECTA], promesa_id=335)
    assert _publicados(conn) == {("57-1", "veredicto", "cumple")}
    assert _publicados(conn, descartados={("57-1", 335, "PP")}) == set()


def test_the_review_file_reads_confirmed_and_discarded(tmp_path):
    ruta = tmp_path / "revision.json"
    ruta.write_text(json.dumps({
        "confirmados": [{"votacion_id": "160-1", "promesa_id": 4716, "partido": "Junts", "veredicto": "incumple"}],
        "descartados": [{"votacion_id": "57-1", "promesa_id": 335, "partido": "PP", "motivo": "otro objeto"}],
    }), encoding="utf-8")
    assert exportar._confirmados(ruta) == {("160-1", 4716, "Junts", "incumple")}
    assert exportar._descartados(ruta) == {("57-1", 335, "PP")}


# --- votaciones que no expresan postura sobre la iniciativa ------------------------

def _v(expediente, tipo="Acuerdos de Comisiones.", titulo_subgrupo="", texto_subgrupo=""):
    return {"tipo": tipo, "titulo_subgrupo": titulo_subgrupo, "texto_subgrupo": texto_subgrupo,
            "expediente": expediente}


def test_a_dissenting_vote_is_not_a_stance_on_the_report():
    sub, _ = votaciones.clasificar(_v("Votación del voto particular, presentado por el Grupo Parlamentario VOX, "
                                      "al Informe de la Subcomisión de salud mental."))
    assert sub == "texto_alternativo"


def test_senate_amendments_voted_in_block_are_not_the_vote_on_the_law():
    exp = ("Proposición de Ley Orgánica de transferencia de la autopista del Atlántico (AP-9) a Galicia.\n"
           "Votación en bloque de las enmiendas.")
    sub, _ = votaciones.clasificar(_v(exp, tipo="Enmiendas del Senado."))
    assert sub == "parcial"
    from src.electoral import mezclas
    assert mezclas.enmienda_suelta_del_senado("Enmiendas del Senado.", exp)


def test_a_party_mostly_absent_has_no_stance():
    mapa = {"grupos": {"GR": "ERC", "GP": "PP"}, "mixto": []}
    diputados = ([{"diputado": f"erc{i}", "grupo": "GR", "voto": "No vota"} for i in range(6)]
                 + [{"diputado": "erc6", "grupo": "GR", "voto": "No"}]
                 + [{"diputado": f"pp{i}", "grupo": "GP", "voto": "Sí"} for i in range(3)]
                 + [{"diputado": "pp3", "grupo": "GP", "voto": "No vota"}])
    votos = votaciones.votos_por_partido({"fecha": "2024-05-01", "diputados": diputados}, mapa)
    assert "ERC" not in votos
    assert votos["PP"]["voto"] == "Sí"


# --- aviso de revisión ---------------------------------------------------------------

def test_the_review_alert_carries_the_initiative_and_what_to_check():
    c = {"partido": "PP", "voto": "No"}
    p = {"texto": "Reformar la Ley de Secretos Oficiales", "cita": "Aprobaremos una ley…",
         "url_programa_pagina": "https://pp.es/programa.pdf#page=12"}
    v = {"fecha": "2024-02-20", "tipo": "Toma en consideración de Proposiciones de Ley.",
         "expediente": "Proposición de Ley del Grupo Parlamentario Vasco (EAJ-PNV), de secretos oficiales.",
         "url_bocg": "https://www.congreso.es/public_oficiales/L15/CONG/BOCG/B/BOCG-15-B-4-1.PDF",
         "url_sesion": "https://www.congreso.es/sesion/20/02/2024", "url_boe": None,
         "mezcla": {"motivo": "Esta norma también toca asuntos que no anuncia su título: el IRPF."}}
    texto = noche.mensaje_revision(c, p, v, {"votacion_id": "24-1", "promesa_id": 281, "partido": "PP",
                                             "veredicto": "incumple"})
    assert "BOCG-15-B-4-1.PDF" in texto
    assert "congreso.es/sesion" in texto
    assert "el título no basta" in texto
    assert "el IRPF" in texto
    assert "descartados" in texto


# --- programas de 2026 -----------------------------------------------------------------

class _LLMFalso:
    def __init__(self, promesas):
        self.promesas = promesas

    def json(self, *a, **k):
        return {"promesas": self.promesas}


def test_index_lines_are_not_extracted_as_promises(tmp_path):
    conn = _base(tmp_path)
    texto = ("[[p. 3]] Índice Vivienda asequible .......... 45 Sanidad pública .......... 52 "
             "[[p. 45]] Construiremos 100.000 viviendas públicas en alquiler social en cuatro años.")
    conn.execute("INSERT INTO bloques (partido, anio, pagina, texto, url_programa) VALUES ('PSOE', 2026, 3, ?, 'x')",
                 (texto,))
    llm = _LLMFalso([
        {"promesa": "Vivienda asequible", "cita": "Vivienda asequible .......... 45", "tema": "Vivienda"},
        {"promesa": "Construir 100.000 viviendas públicas en alquiler social",
         "cita": "Construiremos 100.000 viviendas públicas en alquiler social en cuatro años", "tema": "Vivienda"},
    ])
    programas.extraer(conn, llm)
    assert [r["pagina"] for r in conn.execute("SELECT pagina FROM promesas")] == [45]
