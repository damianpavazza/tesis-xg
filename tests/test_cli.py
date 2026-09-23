from tesis_xg.cli import _resolver_ligas
from tesis_xg.config import Config, HttpConfig, LigasConfig, RutasConfig


def _config_de_prueba() -> Config:
    return Config(
        rutas=RutasConfig(cache="data/cache", base_datos="data/tesis.db", modelos="modelos"),
        http=HttpConfig(espera_entre_solicitudes=1.0, reintentos=3),
        ligas=LigasConfig(codigos=["EPL", "La_liga"], temporada_desde=2014, temporada_hasta=2025),
    )


def test_resolver_ligas_todas_usa_config() -> None:
    assert _resolver_ligas("todas", _config_de_prueba()) == ["EPL", "La_liga"]


def test_resolver_ligas_lista_explicita() -> None:
    assert _resolver_ligas("EPL, Serie_A ,Bundesliga", _config_de_prueba()) == [
        "EPL", "Serie_A", "Bundesliga",
    ]
