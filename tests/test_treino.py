# Testa o baseline e as funções auxiliares do treino (training/baseline.py e training/train.py).

import numpy as np
import pandas as pd
import pytest

from training.baseline import RegraTemperatura
from training.train import avaliar, dividir_por_tempo


def test_baseline_aprende_os_limites_que_separam_as_classes():
    temperaturas = np.array([20, 22, 24, 28, 29, 30, 34, 36])
    rotulos = np.array(["baixo", "baixo", "baixo", "medio", "medio", "medio", "alto", "alto"])

    regra = RegraTemperatura().fit(temperaturas, rotulos)

    assert list(regra.predict(temperaturas)) == list(rotulos)
    assert 24 < regra.limite_medio_c <= 28
    assert 30 < regra.limite_alto_c <= 34


def test_baseline_sem_fit_falha():
    with pytest.raises(RuntimeError):
        RegraTemperatura().predict(np.array([30]))


def test_divisao_por_tempo_nao_mistura_anos():
    dataset = pd.DataFrame({"data": ["2023-06-01", "2024-12-31", "2025-01-01", "2025-07-01"]})

    treino, teste = dividir_por_tempo(dataset)

    assert treino["data"].max() < teste["data"].min()
    assert len(treino) == 2 and len(teste) == 2


def test_avaliar_monta_matriz_na_ordem_baixo_medio_alto():
    real = pd.Series(["baixo", "medio", "alto", "alto"])
    previsto = np.array(["baixo", "medio", "medio", "alto"])

    resultado = avaliar("teste", real, previsto)

    assert resultado["matriz_confusao"] == [[1, 0, 0], [0, 1, 0], [0, 1, 1]]
    assert resultado["por_classe"]["alto"]["recall"] == 0.5
