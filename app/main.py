# Rotas FastAPI do módulo de IA: /health, /bairros e /alerta. Ponto de entrada do serviço.
# Rodar com: uvicorn app.main:app --reload --port 8000   (Swagger em /docs)
#
# As peças (modelo, catálogo, clientes) são criadas uma vez na subida, em criar_servico().
# Os testes chamam criar_app() com um ServicoAlerta montado com peças falsas.

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from app.config import carregar_config
from app.schemas import AlertaRequest, AlertaResponse, BairrosResponse, HealthResponse
from app.services.alerta import BairroDesconhecido, ServicoAlerta
from app.services.bairros import CatalogoBairros
from app.services.clima import ClimaIndisponivel
from app.services.llm import criar_llm
from app.services.refugio_client import RefugioClient
from app.services.risco import ModeloIndisponivel, ModeloRisco

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def criar_servico() -> ServicoAlerta:
    """Monta o serviço real a partir do .env e dos arquivos em data/ e models/."""
    config = carregar_config()
    modelo = ModeloRisco()
    if not modelo.carregado:
        logger.warning(modelo.erro)
    llm = criar_llm(config)
    if hasattr(llm, "aquecer"):
        # Em segundo plano: a API já responde enquanto o Ollama carrega o modelo.
        threading.Thread(target=llm.aquecer, name="aquecer-llm", daemon=True).start()
    return ServicoAlerta(config, CatalogoBairros.do_csv(), modelo, RefugioClient(config), llm)


def criar_app(servico: ServicoAlerta | None = None) -> FastAPI:
    """Cria a aplicação FastAPI.

    Parâmetros:
        servico: serviço já montado (testes). Se None, é criado na subida com criar_servico().
    """

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        app.state.servico = servico or criar_servico()
        yield

    app = FastAPI(
        title="Refúgio IA",
        description="Risco de calor por bairro (ML) e alerta em linguagem simples (LLM) para pessoas idosas.",
        version="1.0.0",
        lifespan=ciclo_de_vida,
    )

    @app.get("/health", response_model=HealthResponse, tags=["Serviço"])
    def health(request: Request) -> HealthResponse:
        """Diz se o serviço está no ar e se o modelo de risco foi carregado."""
        return HealthResponse(modelo_carregado=request.app.state.servico.modelo.carregado)

    @app.get("/bairros", response_model=BairrosResponse, tags=["Alerta"])
    def bairros(request: Request) -> BairrosResponse:
        """Lista os bairros (distritos de São Paulo) que o modelo conhece."""
        return BairrosResponse(bairros=request.app.state.servico.catalogo.nomes())

    @app.post(
        "/alerta",
        response_model=AlertaResponse,
        tags=["Alerta"],
        responses={404: {"description": "Bairro não encontrado"}, 503: {"description": "Modelo ou clima indisponível"}},
    )
    def alerta(pedido: AlertaRequest, request: Request) -> AlertaResponse:
        """Classifica o risco de calor do bairro e devolve o alerta em linguagem simples.

        Sem temperatura_c e umidade_pct, usa a previsão de hoje do Open-Meteo (pior hora do dia).
        """
        try:
            return request.app.state.servico.gerar(pedido)
        except BairroDesconhecido:
            raise HTTPException(404, f"Bairro '{pedido.bairro}' não encontrado. Veja a lista em GET /bairros.")
        except ModeloIndisponivel as erro:
            raise HTTPException(503, str(erro))
        except ClimaIndisponivel as erro:
            raise HTTPException(
                503, f"{erro}. Tente de novo ou envie temperatura_c e umidade_pct para simular o clima."
            )

    return app


app = criar_app()
