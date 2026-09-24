from __future__ import annotations

import argparse
import json
import logging

import requests

from tesis_xg.almacenamiento import base, carga
from tesis_xg.config import Config, cargar_config
from tesis_xg.ingesta import understat
from tesis_xg.ingesta.cliente import ClienteHTTP
from tesis_xg.modelo import aplicar as aplicar_modulo
from tesis_xg.modelo import entrenar as entrenar_modulo
from tesis_xg.modelo import evaluar as evaluar_modulo
from tesis_xg.modelo import features

logger = logging.getLogger(__name__)


def _crear_cliente(config: Config) -> ClienteHTTP:
    return ClienteHTTP(
        directorio_cache=config.rutas.cache,
        espera_entre_solicitudes=config.http.espera_entre_solicitudes,
        reintentos=config.http.reintentos,
        headers=understat.HEADERS,
    )


def _resolver_ligas(valor: str, config: Config) -> list[str]:
    if valor == "todas":
        return config.ligas.codigos
    return [codigo.strip() for codigo in valor.split(",") if codigo.strip()]


def _comando_descargar(args: argparse.Namespace) -> None:
    """Descarga liga(s) x temporada(s) completas: ligas, calendario y cada partido.

    Reanudable: cada respuesta se cachea en disco antes de seguir, así que
    interrumpir el proceso (Ctrl+C, corte de red) y volver a correr el
    mismo comando retoma donde quedó sin re-pedir lo ya descargado. Un
    error puntual (por ejemplo una temporada sin datos) se registra y no
    interrumpe el resto de la descarga.
    """
    config = cargar_config()
    cliente = _crear_cliente(config)

    codigos = _resolver_ligas(args.ligas, config)
    desde = args.desde if args.desde is not None else config.ligas.temporada_desde
    hasta = args.hasta if args.hasta is not None else config.ligas.temporada_hasta
    temporadas = list(range(desde, hasta + 1))

    combinaciones = [(codigo, temporada) for codigo in codigos for temporada in temporadas]
    print(f"{len(combinaciones)} combinación(es) de liga/temporada a procesar")

    total_partidos = 0
    for indice, (codigo, temporada) in enumerate(combinaciones, start=1):
        try:
            liga = understat.descargar_liga(cliente, codigo, temporada)
            ids = understat.ids_de_partidos(cliente, codigo, temporada)
        except requests.RequestException as exc:
            logger.error("no se pudo descargar %s %s: %s", codigo, temporada, exc)
            continue

        print(
            f"[{indice}/{len(combinaciones)}] {codigo} {temporada}: "
            f"{len(liga['teams'])} equipos, {len(ids)} partidos"
        )

        for partido_id in ids:
            try:
                understat.descargar_partido(cliente, partido_id)
                total_partidos += 1
            except requests.RequestException as exc:
                logger.error("no se pudo descargar el partido %s: %s", partido_id, exc)

    print(f"\nListo: {total_partidos} partido(s) verificados (caché o red) en esta corrida")


def _comando_cargar(args: argparse.Namespace) -> None:
    config = cargar_config()
    conexion = base.crear(config.rutas.base_datos)
    try:
        carga.cargar_todo(conexion, config.rutas.cache)
        print()
        print(carga.informe_validacion(conexion))
    finally:
        conexion.close()


def _comando_entrenar(args: argparse.Namespace) -> None:
    config = cargar_config()
    conexion = base.crear(config.rutas.base_datos)
    try:
        features.completar_variables_derivadas(conexion)
        info = entrenar_modulo.entrenar(conexion, config.rutas.modelos)
        print(json.dumps(info, ensure_ascii=False, indent=2))
    finally:
        conexion.close()


def _comando_evaluar(args: argparse.Namespace) -> None:
    config = cargar_config()
    conexion = base.crear(config.rutas.base_datos)
    try:
        metricas = evaluar_modulo.evaluar(conexion, config.rutas.modelos)
        print(json.dumps(metricas, ensure_ascii=False, indent=2))
    finally:
        conexion.close()


def _comando_calcular_xg(args: argparse.Namespace) -> None:
    """Comando aparte que completa `xg_propio` en toda la tabla `disparo`
    (sección 6.3): no-penales vía el modelo, penales vía la tasa de
    conversión histórica calculada al entrenar."""
    config = cargar_config()
    conexion = base.crear(config.rutas.base_datos)
    try:
        features.completar_variables_derivadas(conexion)
        resultado = aplicar_modulo.calcular_xg_propio(conexion, config.rutas.modelos)
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
    finally:
        conexion.close()


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tesis_xg")
    subparsers = parser.add_subparsers(dest="comando", required=True)

    descargar = subparsers.add_parser("descargar", help="Descarga datos de Understat")
    descargar.add_argument("--ligas", default="todas", help="Códigos separados por coma, o 'todas'")
    descargar.add_argument("--desde", type=int, default=None, help="Temporada inicial (año de inicio)")
    descargar.add_argument("--hasta", type=int, default=None, help="Temporada final (año de inicio)")
    descargar.set_defaults(func=_comando_descargar)

    cargar = subparsers.add_parser("cargar", help="Carga la caché descargada en la base SQLite")
    cargar.set_defaults(func=_comando_cargar)

    entrenar = subparsers.add_parser("entrenar", help="Entrena el modelo de xG propio")
    entrenar.set_defaults(func=_comando_entrenar)

    evaluar = subparsers.add_parser("evaluar", help="Evalúa el modelo contra el conjunto de prueba")
    evaluar.set_defaults(func=_comando_evaluar)

    calcular_xg = subparsers.add_parser(
        "calcular-xg", help="Completa xg_propio en toda la tabla disparo"
    )
    calcular_xg.set_defaults(func=_comando_calcular_xg)

    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = construir_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
