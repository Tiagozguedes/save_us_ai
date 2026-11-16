# Regra que gera o rótulo de risco (baixo, medio, alto) do dataset; usada por build_dataset.py.
#
# ATENÇÃO: o rótulo é DERIVADO, não observado. Não existe dado público de risco de calor por
# bairro, então o risco é calculado a partir do índice de calor da NOAA e da proporção de
# idosos. O modelo de ML aprende a reproduzir esta regra a partir de temperatura, umidade e
# % de 60+. Métrica alta = consistência com a regra, não acerto no mundo real.

from __future__ import annotations

from app.config import LIMIAR_RISCO_ALTO_C, LIMIAR_RISCO_MEDIO_C, PESO_IDOSOS_C_POR_PP


def indice_ajustado(indice_calor_c: float, pct_60_mais: float, pct_60_mais_cidade: float) -> float:
    """Índice de calor somado ao ajuste pela proporção de idosos do bairro.

    Parâmetros:
        indice_calor_c: índice de calor da pior hora do dia (°C).
        pct_60_mais: % de moradores com 60 anos ou mais no bairro (0 a 100).
        pct_60_mais_cidade: mesma proporção para a cidade inteira, usada como referência.

    Retorno:
        Índice em °C. Bairro mais idoso que a cidade sobe; menos idoso desce.
    """
    return indice_calor_c + PESO_IDOSOS_C_POR_PP * (pct_60_mais - pct_60_mais_cidade)


def rotular_risco(indice_calor_c: float, pct_60_mais: float, pct_60_mais_cidade: float) -> str:
    """Classifica o dia do bairro em 'baixo', 'medio' ou 'alto' pelas faixas da NOAA.

    Retorno:
        'alto' a partir de LIMIAR_RISCO_ALTO_C, 'medio' a partir de LIMIAR_RISCO_MEDIO_C,
        'baixo' abaixo disso (limites em app/config.py).
    """
    valor = indice_ajustado(indice_calor_c, pct_60_mais, pct_60_mais_cidade)
    if valor >= LIMIAR_RISCO_ALTO_C:
        return "alto"
    if valor >= LIMIAR_RISCO_MEDIO_C:
        return "medio"
    return "baixo"
