# Calcula o índice de calor (sensação térmica no calor) pela fórmula da NOAA.
# Usado por clima.py (pior hora do dia), training/build_dataset.py (rótulo) e alerta.py (resposta).
#
# Referência: NOAA/NWS, "The Heat Index Equation" (Rothfusz, 1990, com os ajustes de umidade
# baixa e alta). https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml
# A fórmula foi ajustada em Fahrenheit, então convertemos na entrada e na saída.
# Os coeficientes abaixo são os da regressão publicada; não são limiares do projeto.

from __future__ import annotations

import math

# Abaixo desta média (°F) a NOAA manda usar a fórmula simples de Steadman, não a regressão.
_LIMIAR_REGRESSAO_F = 80.0


def indice_calor_c(temperatura_c: float, umidade_pct: float) -> float:
    """Devolve o índice de calor em °C.

    Parâmetros:
        temperatura_c: temperatura do ar em °C.
        umidade_pct: umidade relativa de 0 a 100.

    Retorno:
        Índice de calor em °C. Em dia ameno fica perto da própria temperatura.

    Erros:
        ValueError se a umidade estiver fora de 0 a 100.
    """
    if not 0 <= umidade_pct <= 100:
        raise ValueError(f"Umidade precisa estar entre 0 e 100, veio {umidade_pct}")

    t = _c_para_f(temperatura_c)
    ur = umidade_pct

    simples = 0.5 * (t + 61.0 + (t - 68.0) * 1.2 + ur * 0.094)
    if (simples + t) / 2 < _LIMIAR_REGRESSAO_F:
        return _f_para_c(simples)

    hi = (
        -42.379
        + 2.04901523 * t
        + 10.14333127 * ur
        - 0.22475541 * t * ur
        - 0.00683783 * t * t
        - 0.05481717 * ur * ur
        + 0.00122874 * t * t * ur
        + 0.00085282 * t * ur * ur
        - 0.00000199 * t * t * ur * ur
    )

    # Ajustes da própria NOAA para os extremos de umidade.
    if ur < 13 and 80 <= t <= 112:
        hi -= ((13 - ur) / 4) * math.sqrt((17 - abs(t - 95.0)) / 17)
    elif ur > 85 and 80 <= t <= 87:
        hi += ((ur - 85) / 10) * ((87 - t) / 5)

    return _f_para_c(hi)


def _c_para_f(c: float) -> float:
    return c * 9 / 5 + 32


def _f_para_c(f: float) -> float:
    return (f - 32) * 5 / 9
