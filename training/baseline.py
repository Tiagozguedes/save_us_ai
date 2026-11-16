# Baseline por regra simples, usado por train.py para comparar com os modelos de ML.
#
# A regra olha só a temperatura do ar, como alguém que decide pelo termômetro: abaixo de
# um limite é risco baixo, entre os dois é médio, acima é alto. Os dois limites são
# escolhidos no conjunto de treino (o que dá a melhor macro-F1), para a comparação ser justa:
# o modelo de ML precisa ganhar de uma regra bem ajustada, não de uma regra chutada.

from __future__ import annotations

import numpy as np
from sklearn.metrics import f1_score

from app.config import NIVEIS_RISCO

# Faixa e passo da busca dos limites, em °C. Cobre o clima de São Paulo com folga.
_BUSCA_INICIO_C = 18.0
_BUSCA_FIM_C = 40.0
_BUSCA_PASSO_C = 0.5


class RegraTemperatura:
    """Classifica pelo valor da temperatura do ar, com dois limites aprendidos no treino."""

    def __init__(self) -> None:
        self.limite_medio_c: float | None = None
        self.limite_alto_c: float | None = None

    def fit(self, temperaturas: np.ndarray, rotulos: np.ndarray) -> "RegraTemperatura":
        """Escolhe os limites que dão a maior macro-F1 nos dados de treino.

        Parâmetros:
            temperaturas: temperatura do ar (°C) de cada linha.
            rotulos: risco verdadeiro ('baixo', 'medio', 'alto') de cada linha.
        """
        candidatos = np.arange(_BUSCA_INICIO_C, _BUSCA_FIM_C + _BUSCA_PASSO_C, _BUSCA_PASSO_C)
        melhor = (-1.0, None, None)
        for medio in candidatos:
            for alto in candidatos[candidatos > medio]:
                previsto = _aplicar(temperaturas, medio, alto)
                nota = f1_score(rotulos, previsto, average="macro", labels=list(NIVEIS_RISCO))
                if nota > melhor[0]:
                    melhor = (nota, medio, alto)
        _, self.limite_medio_c, self.limite_alto_c = melhor
        return self

    def predict(self, temperaturas: np.ndarray) -> np.ndarray:
        """Aplica os limites aprendidos.

        Erros:
            RuntimeError se fit() ainda não foi chamado.
        """
        if self.limite_medio_c is None:
            raise RuntimeError("Chame fit() antes de predict()")
        return _aplicar(temperaturas, self.limite_medio_c, self.limite_alto_c)


def _aplicar(temperaturas: np.ndarray, medio: float, alto: float) -> np.ndarray:
    return np.where(temperaturas >= alto, "alto", np.where(temperaturas >= medio, "medio", "baixo"))
