# Carrega o modelo treinado (models/modelo_risco.joblib) e classifica o risco; usado por alerta.py.
#
# O serviço sobe mesmo sem o modelo: /health mostra modelo_carregado: false e /alerta responde
# 503 com a instrução de treinar. Assim um clone novo do repositório não quebra na inicialização.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import pandas as pd

from app.config import CAMINHO_MODELO, NIVEIS_RISCO


class ModeloIndisponivel(Exception):
    """O arquivo do modelo não existe ou não pôde ser lido. Rode python -m training.train."""


@dataclass(frozen=True)
class Classificacao:
    """Resultado do modelo para um bairro em um dia."""

    risco: str
    probabilidades: dict[str, float]


class ModeloRisco:
    """Envolve o Random Forest salvo pelo treino."""

    def __init__(self, caminho: Path = CAMINHO_MODELO) -> None:
        """Tenta carregar o modelo. Se falhar, guarda o motivo e fica 'não carregado'."""
        self._modelo = None
        self._features: list[str] = []
        self.erro: str | None = None
        try:
            pacote = joblib.load(caminho)
            self._modelo = pacote["modelo"]
            self._features = list(pacote["features"])
        except FileNotFoundError:
            self.erro = f"Modelo não encontrado em {caminho.name}. Rode: python -m training.train"
        except Exception as erro:  # arquivo corrompido ou de outra versão do scikit-learn
            self.erro = f"Não foi possível ler o modelo ({type(erro).__name__}). Rode: python -m training.train"

    @property
    def carregado(self) -> bool:
        """True se o modelo está pronto para classificar."""
        return self._modelo is not None

    def classificar(self, temperatura_c: float, umidade_pct: float, pct_60_mais: float) -> Classificacao:
        """Classifica o risco de calor.

        Parâmetros:
            temperatura_c, umidade_pct: clima da pior hora do dia (ou o simulado no pedido).
            pct_60_mais: % de moradores com 60+ no bairro (Censo 2022).

        Retorno:
            Classificacao com o nível de maior probabilidade e as três probabilidades.

        Erros:
            ModeloIndisponivel se o modelo não foi carregado.
        """
        if self._modelo is None:
            raise ModeloIndisponivel(self.erro or "Modelo não carregado")

        valores = {"temperatura_c": temperatura_c, "umidade_pct": umidade_pct, "pct_60_mais": pct_60_mais}
        # DataFrame com os nomes de coluna do treino, na mesma ordem.
        entrada = pd.DataFrame([[valores[f] for f in self._features]], columns=self._features)
        probs = self._modelo.predict_proba(entrada)[0]
        por_classe = dict(zip(self._modelo.classes_, probs))

        probabilidades = {nivel: round(float(por_classe.get(nivel, 0.0)), 4) for nivel in NIVEIS_RISCO}
        risco = max(probabilidades, key=probabilidades.get)
        return Classificacao(risco=risco, probabilidades=probabilidades)
