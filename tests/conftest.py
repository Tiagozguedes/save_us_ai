# Peças falsas compartilhadas pelos testes da API (test_endpoints.py e test_cenarios_falha.py).
# Montam um ServicoAlerta sem rede: clima, API .NET e LLM são substituídos por objetos de teste.

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import carregar_config
from app.main import criar_app
from app.schemas import RefugioResumo
from app.services.alerta import ServicoAlerta
from app.services.bairros import CatalogoBairros
from app.services.clima import Clima
from app.services.risco import Classificacao

BIBLIOTECA = RefugioResumo(id=1, nome="Biblioteca Municipal da Penha", vagas_disponiveis=18)
CEU = RefugioResumo(id=2, nome="CEU Penha", vagas_disponiveis=40)
LOTADO = RefugioResumo(id=3, nome="UBS Lotada", vagas_disponiveis=0)


class ModeloFalso:
    """Classifica pelo calor, como o modelo real faria nos casos simples dos testes."""

    carregado = True
    erro = None

    def __init__(self):
        self.entradas = []

    def classificar(self, temperatura_c, umidade_pct, pct_60_mais):
        self.entradas.append((temperatura_c, umidade_pct, pct_60_mais))
        risco = "alto" if temperatura_c >= 33 else "medio" if temperatura_c >= 27 else "baixo"
        probabilidades = {n: (0.9 if n == risco else 0.05) for n in ("baixo", "medio", "alto")}
        return Classificacao(risco=risco, probabilidades=probabilidades)


class RefugiosFalsos:
    """Imita o RefugioClient: devolve uma lista fixa ou levanta o erro configurado."""

    def __init__(self, refugios=None, erro=None):
        self.refugios = [BIBLIOTECA, CEU, LOTADO] if refugios is None else refugios
        self.erro = erro
        self.bairros_pedidos = []

    def listar_ativos(self, bairro):
        self.bairros_pedidos.append(bairro)
        if self.erro:
            raise self.erro
        return self.refugios


class LLMFalso:
    """Guarda os prompts e devolve um texto que cita o primeiro refúgio do prompt."""

    def __init__(self, resposta=None, erro=None):
        self.resposta, self.erro, self.prompts = resposta, erro, []

    def gerar(self, prompt):
        self.prompts.append(prompt)
        if self.erro:
            raise self.erro
        if self.resposta is not None:
            return self.resposta
        return "Hoje o calor está perigoso na Penha. Vá para o CEU Penha. Beba água. Se passar mal, ligue 192."


def clima_fixo(temperatura=34.2, umidade=48.0):
    def obter(latitude, longitude, config):
        return Clima(temperatura_c=temperatura, umidade_pct=umidade, indice_calor_c=36.0, hora="2026-11-16T15:00")

    return obter


@pytest.fixture
def pecas():
    """Peças padrão; cada teste troca a que precisar antes de pedir o cliente."""
    return {
        "modelo": ModeloFalso(),
        "refugios": RefugiosFalsos(),
        "llm": LLMFalso(),
        "obter_clima": clima_fixo(),
    }


@pytest.fixture
def cliente(pecas):
    """TestClient da API com as peças do fixture `pecas`."""
    servico = ServicoAlerta(
        carregar_config({}),
        CatalogoBairros.do_csv(),
        pecas["modelo"],
        pecas["refugios"],
        pecas["llm"],
        obter_clima=pecas["obter_clima"],
    )
    with TestClient(criar_app(servico)) as c:
        yield c
