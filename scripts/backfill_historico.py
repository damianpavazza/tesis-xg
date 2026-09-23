"""Descarga y carga histórica completa, con corte de validación por temporada.

No es parte del CLI documentado en la sección 2 de la especificación
(descargar/cargar/entrenar/evaluar/dashboard): es una herramienta operativa
de una sola vez para construir el dataset histórico completo, reutilizando
esas mismas funciones. Ver DESVIACIONES.md, sección "Backfill histórico".

Para cada temporada (en orden), descarga las 5 ligas configuradas, carga
todo en la base y corre chequeos de calidad sobre esa temporada antes de
avanzar a la siguiente. Si un chequeo falla, se detiene: es más barato
pausar y revisar que seguir corriendo horas sobre datos con un problema
no detectado.

Uso:
    python scripts/backfill_historico.py [--desde 2014] [--hasta 2025]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import requests  # noqa: E402

from tesis_xg.almacenamiento import base, carga  # noqa: E402
from tesis_xg.config import Config, cargar_config  # noqa: E402
from tesis_xg.ingesta import understat  # noqa: E402
from tesis_xg.ingesta.cliente import ClienteHTTP  # noqa: E402

logger = logging.getLogger("backfill")

# Partidos confirmados manualmente como huecos reales de la fuente (no
# fallos de descarga): el validador no los cuenta como "sin disparos".
# Cualquier partido sin disparos que NO esté acá sigue deteniendo el
# backfill para revisión.
EXCEPCIONES_SIN_DISPAROS: dict[int, str] = {
    4238: (
        "SC Bastia vs Lyon, Ligue_1 2016/17 (2017-04-16): partido no "
        "disputado por incidentes de la hinchada de Bastia; resultado "
        "3-0 otorgado a Lyon por decisión administrativa. Understat no "
        "tiene alineaciones ni disparos porque no se jugó."
    ),
}


def _crear_cliente(config: Config) -> ClienteHTTP:
    return ClienteHTTP(
        directorio_cache=config.rutas.cache,
        espera_entre_solicitudes=config.http.espera_entre_solicitudes,
        reintentos=config.http.reintentos,
        headers=understat.HEADERS,
    )


def _descargar_temporada(cliente: ClienteHTTP, codigos: list[str], temporada: int) -> None:
    for codigo in codigos:
        try:
            liga = understat.descargar_liga(cliente, codigo, temporada)
            ids = understat.ids_de_partidos(cliente, codigo, temporada)
        except requests.RequestException as exc:
            logger.error("no se pudo descargar %s %s: %s", codigo, temporada, exc)
            continue

        print(f"  {codigo} {temporada}: {len(liga['teams'])} equipos, {len(ids)} partidos")
        for partido_id in ids:
            try:
                understat.descargar_partido(cliente, partido_id)
            except requests.RequestException as exc:
                logger.error("no se pudo descargar el partido %s: %s", partido_id, exc)


def _validar_temporada(conexion, codigos: list[str], temporada: int) -> list[str]:
    """Devuelve los problemas encontrados para esta temporada (vacía si está OK)."""
    problemas: list[str] = []

    for codigo in codigos:
        (n_partidos,) = conexion.execute(
            """
            SELECT COUNT(*) FROM partido p
            JOIN temporada t ON t.id = p.temporada_id
            JOIN liga l ON l.id = t.liga_id
            WHERE l.codigo = ? AND t.anio_inicio = ?
            """,
            (codigo, temporada),
        ).fetchone()

        if n_partidos == 0:
            problemas.append(f"{codigo} {temporada}: 0 partidos cargados (¿falló la descarga?)")
            continue

        ids_sin_disparos = [
            fila[0]
            for fila in conexion.execute(
                """
                SELECT p.id FROM partido p
                JOIN temporada t ON t.id = p.temporada_id
                JOIN liga l ON l.id = t.liga_id
                WHERE l.codigo = ? AND t.anio_inicio = ?
                  AND NOT EXISTS (SELECT 1 FROM disparo d WHERE d.partido_id = p.id)
                """,
                (codigo, temporada),
            )
        ]
        nuevos_sin_disparos = [pid for pid in ids_sin_disparos if pid not in EXCEPCIONES_SIN_DISPAROS]
        for pid in ids_sin_disparos:
            if pid in EXCEPCIONES_SIN_DISPAROS:
                print(f"    (excepción conocida) partido {pid}: {EXCEPCIONES_SIN_DISPAROS[pid]}")
        if nuevos_sin_disparos:
            problemas.append(
                f"{codigo} {temporada}: {len(nuevos_sin_disparos)} partido(s) sin ningún disparo "
                f"cargado y sin excepción conocida: {nuevos_sin_disparos}"
            )

        (disparos_sin_jugador,) = conexion.execute(
            """
            SELECT COUNT(*) FROM disparo d
            JOIN partido p ON p.id = d.partido_id
            JOIN temporada t ON t.id = p.temporada_id
            JOIN liga l ON l.id = t.liga_id
            WHERE l.codigo = ? AND t.anio_inicio = ? AND d.jugador_id IS NULL
            """,
            (codigo, temporada),
        ).fetchone()
        if disparos_sin_jugador:
            problemas.append(f"{codigo} {temporada}: {disparos_sin_jugador} disparo(s) sin jugador_id")

        print(f"  {codigo} {temporada}: {n_partidos} partidos cargados, OK")

    return problemas


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--desde", type=int, default=None)
    parser.add_argument("--hasta", type=int, default=None)
    args = parser.parse_args()

    config = cargar_config()
    cliente = _crear_cliente(config)
    codigos = config.ligas.codigos
    desde = args.desde if args.desde is not None else config.ligas.temporada_desde
    hasta = args.hasta if args.hasta is not None else config.ligas.temporada_hasta

    for temporada in range(desde, hasta + 1):
        print(f"\n=== Temporada {temporada} ===", flush=True)
        _descargar_temporada(cliente, codigos, temporada)

        conexion = base.crear(config.rutas.base_datos)
        try:
            carga.cargar_todo(conexion, config.rutas.cache)
            problemas = _validar_temporada(conexion, codigos, temporada)
        finally:
            conexion.close()

        if problemas:
            print(f"\nSE DETUVO EN LA TEMPORADA {temporada} — problemas encontrados:", flush=True)
            for problema in problemas:
                print(f"  - {problema}")
            sys.exit(1)

    print("\nDescarga histórica completa: todas las temporadas validadas OK", flush=True)


if __name__ == "__main__":
    main()
