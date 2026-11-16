# Busca no Open-Meteo a temperatura e a umidade de hoje para um ponto; usado por alerta.py.
#
# Por que a "pior hora do dia": o alerta vale para o dia inteiro. Pegamos a previsão hora a
# hora de hoje e escolhemos a hora com maior índice de calor. O treino (build_dataset.py)
# usa a mesma regra no histórico, então o modelo recebe em produção o mesmo tipo de entrada
# que viu no treino.

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import FUSO_HORARIO, OPEN_METEO_PREVISAO_URL, Config
from app.services.indice_calor import indice_calor_c

VARIAVEIS_HORARIAS = "temperature_2m,relative_humidity_2m"


class ClimaIndisponivel(Exception):
    """O Open-Meteo não respondeu ou mandou dados incompletos.

    Sem clima não há como classificar o risco. Quem chama devolve erro claro e sugere
    enviar temperatura_c e umidade_pct para simular.
    """


@dataclass(frozen=True)
class Clima:
    """Clima da pior hora do dia em um ponto."""

    temperatura_c: float
    umidade_pct: float
    indice_calor_c: float
    hora: str  # ISO local de São Paulo, ex.: "2026-11-16T15:00"


def obter_clima_do_dia(latitude: float, longitude: float, config: Config, http: httpx.Client | None = None) -> Clima:
    """Consulta a previsão horária de hoje e devolve a hora de maior índice de calor.

    Parâmetros:
        latitude, longitude: ponto do bairro (centro do distrito, ver data/processed/bairros.csv).
        config: usa clima_timeout_s.
        http: cliente httpx opcional; os testes passam um com transporte simulado.

    Retorno:
        Clima com temperatura, umidade e índice de calor da pior hora.

    Erros:
        ClimaIndisponivel em timeout, erro HTTP ou resposta sem nenhuma hora válida.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": VARIAVEIS_HORARIAS,
        "forecast_days": 1,
        "timezone": FUSO_HORARIO,
    }
    cliente = http or httpx.Client(timeout=config.clima_timeout_s)
    try:
        resposta = cliente.get(OPEN_METEO_PREVISAO_URL, params=params)
        resposta.raise_for_status()
        horario = resposta.json()["hourly"]
    except httpx.HTTPError as erro:
        raise ClimaIndisponivel(f"Open-Meteo falhou: {type(erro).__name__}") from erro
    except (ValueError, KeyError) as erro:
        raise ClimaIndisponivel(f"Open-Meteo respondeu em formato inesperado: {erro}") from None
    finally:
        if http is None:
            cliente.close()

    return pior_hora(horario["time"], horario["temperature_2m"], horario["relative_humidity_2m"])


def pior_hora(horas: list[str], temperaturas: list[float | None], umidades: list[float | None]) -> Clima:
    """Escolhe, entre as horas com dado completo, a de maior índice de calor.

    Também usada pelo treino sobre o histórico do Open-Meteo, para manter a mesma regra.

    Erros:
        ClimaIndisponivel se nenhuma hora tiver temperatura e umidade.
    """
    candidatas = [
        Clima(temperatura_c=t, umidade_pct=u, indice_calor_c=indice_calor_c(t, u), hora=h)
        for h, t, u in zip(horas, temperaturas, umidades)
        # O Open-Meteo manda null em horas sem dado.
        if t is not None and u is not None
    ]
    if not candidatas:
        raise ClimaIndisponivel("Open-Meteo não trouxe nenhuma hora com temperatura e umidade")
    return max(candidatas, key=lambda c: c.indice_calor_c)
