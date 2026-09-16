from __future__ import annotations

from tesis_xg.ingesta.cliente import ClienteHTTP

BASE_URL = "https://understat.com"

# Understat sirve estos endpoints solo a solicitudes AJAX: sin esta cabecera
# responden 404. El User-Agent evita bloqueos por tráfico no-navegador.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
}


def descargar_liga(cliente: ClienteHTTP, codigo: str, temporada: int, forzar: bool = False) -> dict:
    """Trae `teams`, `players` y `dates` de una liga/temporada."""
    url = f"{BASE_URL}/getLeagueData/{codigo}/{temporada}"
    nombre_cache = f"liga_{codigo}_{temporada}.json"
    return cliente.obtener_json(url, nombre_cache, forzar=forzar)


def descargar_partido(cliente: ClienteHTTP, partido_id: int, forzar: bool = False) -> dict:
    """Trae `shots` (claves `h`/`a`) y `rosters` de un partido."""
    url = f"{BASE_URL}/getMatchData/{partido_id}"
    nombre_cache = f"partido_{partido_id}.json"
    return cliente.obtener_json(url, nombre_cache, forzar=forzar)


def ids_de_partidos(cliente: ClienteHTTP, codigo: str, temporada: int) -> list[int]:
    """IDs de los partidos ya disputados de una liga/temporada."""
    datos = descargar_liga(cliente, codigo, temporada)
    return [int(partido["id"]) for partido in datos["dates"] if partido["isResult"]]
