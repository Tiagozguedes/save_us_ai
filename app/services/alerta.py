# Orquestra o fluxo completo do POST /alerta; chamado por main.py.
#
#   bairro → clima (Open-Meteo ou simulado) → risco (modelo de ML) → refúgios (API .NET)
#          → texto (LLM, com texto padrão de reserva) → AlertaResponse
#
# Falhas que derrubam o alerta: bairro desconhecido (404), sem modelo ou sem clima (503).
# Falhas que NÃO derrubam: API .NET fora do ar (alerta sem refúgio) e LLM fora do ar (texto padrão).

from __future__ import annotations

import logging
from typing import Callable

from app.config import MAX_REFUGIOS_NO_ALERTA, Config
from app.schemas import AlertaRequest, AlertaResponse, Probabilidades, RefugioResumo
from app.services.bairros import Bairro, CatalogoBairros
from app.services.clima import Clima, obter_clima_do_dia
from app.services.indice_calor import indice_calor_c
from app.services.llm import ClienteLLM, DadosAlerta, escrever_alerta
from app.services.refugio_client import RefugioClient, RefugioIndisponivel
from app.services.risco import ModeloRisco

logger = logging.getLogger(__name__)


class BairroDesconhecido(Exception):
    """O bairro pedido não está entre os 96 distritos que o modelo conhece."""


class ServicoAlerta:
    """Junta as peças do fluxo. main.py cria um por processo; os testes passam peças falsas."""

    def __init__(
        self,
        config: Config,
        catalogo: CatalogoBairros,
        modelo: ModeloRisco,
        refugios: RefugioClient | None,
        llm: ClienteLLM | None,
        obter_clima: Callable[[float, float, Config], Clima] = obter_clima_do_dia,
    ) -> None:
        self.config = config
        self.catalogo = catalogo
        self.modelo = modelo
        self._refugios = refugios
        self._llm = llm
        self._obter_clima = obter_clima

    def gerar(self, pedido: AlertaRequest) -> AlertaResponse:
        """Gera o alerta de calor de um bairro.

        Parâmetros:
            pedido: bairro e, opcionalmente, clima simulado.

        Retorno:
            AlertaResponse completo, sempre com texto de alerta.

        Erros:
            BairroDesconhecido se o bairro não existe no catálogo.
            ModeloIndisponivel se o modelo não foi treinado ou não carregou.
            ClimaIndisponivel se o Open-Meteo falhou e o pedido não trouxe clima simulado.
        """
        bairro = self.catalogo.buscar(pedido.bairro)
        if bairro is None:
            raise BairroDesconhecido(pedido.bairro)

        temperatura, umidade, indice = self._clima(pedido, bairro)
        classificacao = self.modelo.classificar(temperatura, umidade, bairro.pct_60_mais)
        refugios, consultados = self._refugios_com_vaga(bairro.nome)

        dados = DadosAlerta(
            bairro=bairro.nome,
            risco=classificacao.risco,
            temperatura_c=temperatura,
            umidade_pct=umidade,
            indice_calor_c=indice,
            refugios=[r.nome for r in refugios[:MAX_REFUGIOS_NO_ALERTA]],
            refugios_consultados=consultados,
        )
        texto, origem = escrever_alerta(self._llm, dados)

        return AlertaResponse(
            bairro=bairro.nome,
            temperatura_c=round(temperatura, 1),
            umidade_pct=round(umidade),
            indice_calor_c=round(indice, 1),
            risco=classificacao.risco,
            probabilidades=Probabilidades(**classificacao.probabilidades),
            refugios=refugios,
            refugios_consultados=consultados,
            alerta=texto,
            origem_texto=origem,
        )

    def _clima(self, pedido: AlertaRequest, bairro: Bairro) -> tuple[float, float, float]:
        """Usa o clima simulado do pedido ou busca o da pior hora de hoje no Open-Meteo."""
        if pedido.clima_simulado:
            return pedido.temperatura_c, pedido.umidade_pct, indice_calor_c(pedido.temperatura_c, pedido.umidade_pct)
        clima = self._obter_clima(bairro.latitude, bairro.longitude, self.config)
        return clima.temperatura_c, clima.umidade_pct, clima.indice_calor_c

    def _refugios_com_vaga(self, bairro: str) -> tuple[list[RefugioResumo], bool]:
        """Pede os refúgios ativos à API .NET e fica só com os que têm vaga.

        Retorno:
            (refúgios com vaga, do que tem mais vagas para o que tem menos; se a API respondeu).
            Se a API .NET falhar, devolve ([], False) e o alerta segue sem refúgio.
        """
        if self._refugios is None:
            return [], False
        try:
            ativos = self._refugios.listar_ativos(bairro)
        except RefugioIndisponivel as erro:
            logger.warning("API .NET indisponível, alerta sem refúgio: %s", erro)
            return [], False
        com_vaga = sorted((r for r in ativos if r.vagas_disponiveis > 0), key=lambda r: -r.vagas_disponiveis)
        return com_vaga, True
