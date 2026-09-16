from __future__ import annotations

import argparse
import logging

from tesis_xg.config import Config, cargar_config
from tesis_xg.ingesta import understat
from tesis_xg.ingesta.cliente import ClienteHTTP

logger = logging.getLogger(__name__)


def _crear_cliente(config: Config) -> ClienteHTTP:
    return ClienteHTTP(
        directorio_cache=config.rutas.cache,
        espera_entre_solicitudes=config.http.espera_entre_solicitudes,
        reintentos=config.http.reintentos,
        headers=understat.HEADERS,
    )


def _comando_descargar(args: argparse.Namespace) -> None:
    """Etapa 1: trae una liga y su último partido disputado.

    Se irá ampliando en la Etapa 4 a la descarga completa (todas las ligas
    y temporadas configuradas, reanudable ante interrupción).
    """
    config = cargar_config()
    cliente = _crear_cliente(config)

    liga = understat.descargar_liga(cliente, args.liga, args.temporada)
    print(f"Liga {args.liga} {args.temporada}: {len(liga['teams'])} equipos")

    ids = understat.ids_de_partidos(cliente, args.liga, args.temporada)
    print(f"Partidos con resultado: {len(ids)}")

    if ids:
        ultimo_id = ids[-1]
        partido = understat.descargar_partido(cliente, ultimo_id)
        disparos = partido["shots"]
        print(
            f"Partido {ultimo_id}: {len(disparos['h'])} disparos locales, "
            f"{len(disparos['a'])} visitantes"
        )


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tesis_xg")
    subparsers = parser.add_subparsers(dest="comando", required=True)

    descargar = subparsers.add_parser("descargar", help="Descarga datos de Understat")
    descargar.add_argument("--liga", default="EPL")
    descargar.add_argument("--temporada", type=int, default=2025)
    descargar.set_defaults(func=_comando_descargar)

    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = construir_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
