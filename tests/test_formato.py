from tesis_xg.analisis.formato import etiqueta_temporada


def test_etiqueta_temporada() -> None:
    assert etiqueta_temporada(2018) == "2018/19"
    assert etiqueta_temporada(2025) == "2025/26"
    assert etiqueta_temporada(1999) == "1999/00"  # cruce de siglo
    assert etiqueta_temporada(2009) == "2009/10"
