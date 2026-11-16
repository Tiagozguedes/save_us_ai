# Baixa o clima horário histórico do Open-Meteo e resume cada dia pela pior hora;
# usado por build_dataset.py.
#
# Cada distrito é ligado à célula de 0,1° do ERA5-Land em que cai. Baixamos uma vez por
# célula (17 células para os 96 distritos) e guardamos o JSON em data/raw/clima/ para não
# repetir o download.

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pandas as pd

from app.config import (
    FUSO_HORARIO,
    HISTORICO_FIM,
    HISTORICO_GRADE_GRAUS,
    HISTORICO_INICIO,
    HISTORICO_MODELO,
    OPEN_METEO_HISTORICO_URL,
)
from app.services.clima import VARIAVEIS_HORARIAS, pior_hora

# Pedido de três anos horários demora; o arquivo do Open-Meteo responde em alguns segundos.
TIMEOUT_HISTORICO_S = 120
# Pausa entre células para não bater no limite por minuto da camada gratuita.
PAUSA_ENTRE_PEDIDOS_S = 2


def celula(latitude: float, longitude: float) -> tuple[float, float]:
    """Centro da célula da grade do ERA5-Land que contém o ponto."""
    passo = HISTORICO_GRADE_GRAUS
    return round(round(latitude / passo) * passo, 2), round(round(longitude / passo) * passo, 2)


def baixar_celula(lat: float, lon: float, pasta_cache: Path) -> dict:
    """Baixa (ou lê do cache) o histórico horário de uma célula.

    Erros:
        httpx.HTTPError se o Open-Meteo falhar. O treino para: sem clima real não há dataset.
    """
    arquivo = pasta_cache / f"{lat:.2f}_{lon:.2f}_{HISTORICO_INICIO}_{HISTORICO_FIM}.json"
    if arquivo.exists():
        return json.loads(arquivo.read_text(encoding="utf-8"))

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": HISTORICO_INICIO,
        "end_date": HISTORICO_FIM,
        "hourly": VARIAVEIS_HORARIAS,
        "models": HISTORICO_MODELO,
        "timezone": FUSO_HORARIO,
    }
    resposta = httpx.get(OPEN_METEO_HISTORICO_URL, params=params, timeout=TIMEOUT_HISTORICO_S)
    resposta.raise_for_status()
    dados = resposta.json()

    pasta_cache.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps(dados), encoding="utf-8")
    time.sleep(PAUSA_ENTRE_PEDIDOS_S)
    return dados


def pior_hora_por_dia(dados: dict) -> pd.DataFrame:
    """Resume o histórico horário em uma linha por dia, com a hora de maior índice de calor.

    Usa clima.pior_hora(), a mesma função do serviço em produção.

    Retorno:
        DataFrame com data, temperatura_c, umidade_pct e indice_calor_c. Dias sem nenhuma
        hora com dado completo ficam de fora.
    """
    horario = pd.DataFrame(dados["hourly"])
    horario["data"] = horario["time"].str[:10]

    linhas = []
    for dia, grupo in horario.groupby("data", sort=True):
        temperaturas = [None if pd.isna(v) else float(v) for v in grupo["temperature_2m"]]
        umidades = [None if pd.isna(v) else float(v) for v in grupo["relative_humidity_2m"]]
        if all(t is None for t in temperaturas):
            continue
        pior = pior_hora(list(grupo["time"]), temperaturas, umidades)
        linhas.append(
            {
                "data": dia,
                "temperatura_c": pior.temperatura_c,
                "umidade_pct": pior.umidade_pct,
                "indice_calor_c": round(pior.indice_calor_c, 2),
            }
        )
    return pd.DataFrame(linhas)
