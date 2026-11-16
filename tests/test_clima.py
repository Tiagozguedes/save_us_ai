# Testa a consulta ao Open-Meteo (app/services/clima.py) com respostas simuladas.

import httpx
import pytest
import respx

from app.config import OPEN_METEO_PREVISAO_URL, carregar_config
from app.services.clima import ClimaIndisponivel, obter_clima_do_dia, pior_hora

CONFIG = carregar_config({})
PENHA = (-23.52, -46.54)


def previsao(temperaturas, umidades):
    horas = [f"2026-11-16T{h:02d}:00" for h in range(len(temperaturas))]
    return {"hourly": {"time": horas, "temperature_2m": temperaturas, "relative_humidity_2m": umidades}}


@pytest.fixture
def open_meteo():
    with respx.mock(assert_all_called=False) as mock:
        yield mock.get(OPEN_METEO_PREVISAO_URL)


def test_devolve_a_hora_de_maior_indice_de_calor(open_meteo):
    open_meteo.respond(200, json=previsao([20, 33, 31], [80, 50, 85]))

    clima = obter_clima_do_dia(*PENHA, CONFIG, http=httpx.Client())

    # 31 °C com 85% de umidade "pesa" mais que 33 °C com 50%.
    assert (clima.temperatura_c, clima.umidade_pct, clima.hora) == (31, 85, "2026-11-16T02:00")
    assert clima.indice_calor_c > 31

    params = open_meteo.calls.last.request.url.params
    assert params["timezone"] == "America/Sao_Paulo"
    assert params["forecast_days"] == "1"


def test_ignora_horas_sem_dado():
    clima = pior_hora(["a", "b", "c"], [None, 25, 40], [50, 50, None])

    assert clima.hora == "b"


def test_sem_nenhuma_hora_valida_vira_indisponivel():
    with pytest.raises(ClimaIndisponivel):
        pior_hora(["a"], [None], [None])


def test_timeout_vira_indisponivel(open_meteo):
    open_meteo.mock(side_effect=httpx.ConnectTimeout("lento"))

    with pytest.raises(ClimaIndisponivel, match="ConnectTimeout"):
        obter_clima_do_dia(*PENHA, CONFIG, http=httpx.Client())


def test_erro_http_vira_indisponivel(open_meteo):
    open_meteo.respond(500)

    with pytest.raises(ClimaIndisponivel):
        obter_clima_do_dia(*PENHA, CONFIG, http=httpx.Client())


def test_resposta_sem_hourly_vira_indisponivel(open_meteo):
    open_meteo.respond(200, json={"error": True})

    with pytest.raises(ClimaIndisponivel, match="formato inesperado"):
        obter_clima_do_dia(*PENHA, CONFIG, http=httpx.Client())
