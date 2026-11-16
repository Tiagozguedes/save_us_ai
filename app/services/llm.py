# Pede ao LLM o texto do alerta, valida a resposta e cai no texto padrão se algo der errado;
# usado por alerta.py.
#
# Provedor: Ollama local (decisão do grupo). Nenhum dado sai da máquina e não há custo por
# chamada. A interface (gerar(prompt) -> str) deixa trocar de provedor sem mexer no resto.
#
# Dado pessoal: DadosAlerta só tem bairro, risco, números do clima e nomes de refúgios.
# Não existe campo para nome, telefone ou contato do idoso, de propósito.

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from string import Template
from typing import Literal, Protocol

import httpx

from app.config import (
    AFIRMACOES_PROIBIDAS,
    ALERTA_MAX_CARACTERES,
    CAMINHO_GUIA_CALOR,
    CAMINHO_PROMPT,
    LLM_TEMPERATURA,
    MARCA_DOS_EXEMPLOS,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_TIMEOUT_AQUECIMENTO_S,
    PALAVRAS_DE_LUGAR,
    SIGLA_CEU,
    TELEFONE_SAMU,
    Config,
)
from app.services.bairros import normalizar
from app.services.texto_padrao import texto_padrao

logger = logging.getLogger(__name__)

NOMES_RISCO = {"baixo": "baixo", "medio": "médio", "alto": "alto"}


class LLMIndisponivel(Exception):
    """O LLM não respondeu, demorou demais ou respondeu em formato inesperado."""


class ClienteLLM(Protocol):
    """O que o serviço espera de qualquer provedor de LLM."""

    def gerar(self, prompt: str) -> str: ...


@dataclass(frozen=True)
class DadosAlerta:
    """Tudo o que o LLM recebe. Nada aqui identifica a pessoa idosa."""

    bairro: str
    risco: str
    temperatura_c: float
    umidade_pct: float
    indice_calor_c: float
    refugios: list[str]
    refugios_consultados: bool


class OllamaLLM:
    """Cliente do Ollama local (rota /api/chat, sem streaming)."""

    def __init__(self, config: Config, http: httpx.Client | None = None) -> None:
        self._modelo = config.llm_model
        self._http = http or httpx.Client(base_url=config.llm_url, timeout=config.llm_timeout_s)

    def gerar(self, prompt: str) -> str:
        """Envia o prompt e devolve o texto da resposta.

        Erros:
            LLMIndisponivel em timeout, Ollama desligado, modelo não baixado (404) ou
            resposta sem o campo message.content.
        """
        corpo = {
            "model": self._modelo,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "options": {"temperature": LLM_TEMPERATURA},
        }
        try:
            resposta = self._http.post("/api/chat", json=corpo)
            resposta.raise_for_status()
            return resposta.json()["message"]["content"]
        except httpx.HTTPError as erro:
            raise LLMIndisponivel(f"Ollama falhou: {type(erro).__name__}") from erro
        except (ValueError, KeyError, TypeError):
            raise LLMIndisponivel("Ollama respondeu em formato inesperado") from None

    def aquecer(self) -> bool:
        """Carrega o modelo na memória do Ollama, sem gerar texto.

        O Ollama carrega o modelo quando recebe um /api/chat sem mensagens. Chamado em
        segundo plano na subida do serviço, para o primeiro alerta não estourar o timeout.

        Retorno:
            True se o modelo ficou pronto; False se o Ollama não respondeu (o serviço segue,
            e os alertas usam o texto padrão até ele voltar).
        """
        corpo = {"model": self._modelo, "messages": [], "keep_alive": OLLAMA_KEEP_ALIVE}
        try:
            self._http.post("/api/chat", json=corpo, timeout=OLLAMA_TIMEOUT_AQUECIMENTO_S).raise_for_status()
            return True
        except httpx.HTTPError as erro:
            logger.warning("Não foi possível carregar o modelo %s no Ollama: %s", self._modelo, type(erro).__name__)
            return False


def criar_llm(config: Config) -> ClienteLLM | None:
    """Cria o cliente do provedor configurado em LLM_PROVIDER.

    Retorno:
        O cliente, ou None se o provedor não for suportado. Com None, todo alerta usa o
        texto padrão (origem_texto: "fallback"), e o serviço continua respondendo.
    """
    if config.llm_provider == "ollama":
        return OllamaLLM(config)
    logger.warning("LLM_PROVIDER=%r não é suportado; os alertas vão usar o texto padrão", config.llm_provider)
    return None


def escrever_alerta(llm: ClienteLLM | None, dados: DadosAlerta) -> tuple[str, Literal["llm", "fallback"]]:
    """Gera o texto do alerta com o LLM, com texto padrão de reserva.

    Parâmetros:
        llm: cliente do LLM, ou None se não há provedor configurado.
        dados: risco, clima e refúgios (sem dado pessoal).

    Retorno:
        (texto, origem). origem é "llm" se o texto do LLM passou na validação, ou
        "fallback" se o LLM falhou, demorou ou escreveu algo fora das regras.
        Nunca levanta exceção e nunca devolve texto vazio.
    """
    if llm is not None:
        try:
            texto = limpar(llm.gerar(montar_prompt(dados)))
            motivo = motivo_invalido(texto, dados)
            if motivo is None:
                return texto, "llm"
            logger.warning("Texto do LLM recusado (%s): %r", motivo, texto)
        except LLMIndisponivel as erro:
            logger.warning("LLM indisponível: %s", erro)
    return texto_padrao(dados.risco, dados.bairro, dados.refugios), "fallback"


def montar_prompt(dados: DadosAlerta) -> str:
    """Preenche app/prompts/alerta.txt com os dados e o Guia do calor."""
    if dados.refugios:
        lista = "; ".join(dados.refugios)
    elif dados.refugios_consultados:
        lista = "(nenhum refúgio aberto com vaga hoje)"
    else:
        lista = "(lista indisponível agora)"

    linhas = [
        f"Bairro: {dados.bairro}",
        f"Risco de calor hoje: {NOMES_RISCO[dados.risco]}",
        f"Temperatura na hora mais quente: {_numero(dados.temperatura_c)} °C",
        f"Umidade do ar: {_numero(dados.umidade_pct, 0)}%",
        f"Sensação térmica (índice de calor): {_numero(dados.indice_calor_c)} °C",
        f"Refúgios abertos com vaga: {lista}",
    ]
    modelo, guia = _ler_textos()
    return Template(modelo).safe_substitute(dados="\n".join(linhas), guia=guia)


def limpar(texto: str) -> str:
    """Tira marcações que o LLM às vezes põe (asteriscos, aspas em volta, espaços extras)."""
    texto = texto.replace("*", "").replace("#", "")
    texto = " ".join(texto.split())
    return texto.strip().strip('"“”').strip()


def motivo_invalido(texto: str, dados: DadosAlerta) -> str | None:
    """Confere se o texto do LLM segue as regras do alerta.

    Retorno:
        None se o texto é válido; senão, uma frase curta com o motivo (vai para o log).
    """
    if not texto:
        return "texto vazio"
    if len(texto) > ALERTA_MAX_CARACTERES:
        return f"texto com {len(texto)} caracteres, acima de {ALERTA_MAX_CARACTERES}"
    if dados.risco == "alto" and TELEFONE_SAMU not in texto:
        return "risco alto sem o SAMU 192"
    numeros_longos = [n for n in re.findall(r"\d+", texto) if len(n) >= 3 and n != TELEFONE_SAMU]
    if numeros_longos:
        return f"número que parece telefone ou endereço: {numeros_longos}"
    texto_normalizado = normalizar(texto)
    if MARCA_DOS_EXEMPLOS in texto_normalizado:
        return "copiou nome dos exemplos do prompt"
    for afirmacao in AFIRMACOES_PROIBIDAS:
        if afirmacao in texto_normalizado:
            return f"afirma algo que a API não informa: {afirmacao!r}"

    # Tira do texto os refúgios permitidos; qualquer lugar que sobrar foi inventado pelo LLM.
    sobra = texto
    for nome in dados.refugios:
        sobra = re.sub(re.escape(nome), " ", sobra, flags=re.IGNORECASE)
    sobra_normalizada = normalizar(sobra)
    for palavra in PALAVRAS_DE_LUGAR:
        if re.search(rf"\b{re.escape(palavra)}\b", sobra_normalizada):
            return f"cita lugar fora da lista de refúgios: {palavra!r}"
    if re.search(rf"\b{SIGLA_CEU}\b", sobra):
        return "cita um CEU fora da lista de refúgios"

    citou_refugio = any(re.search(re.escape(nome), texto, flags=re.IGNORECASE) for nome in dados.refugios)
    if dados.risco == "alto" and dados.refugios and not citou_refugio:
        return "risco alto com refúgio disponível, mas o texto não cita nenhum"
    return None


@lru_cache(maxsize=1)
def _ler_textos() -> tuple[str, str]:
    """Lê o prompt e o guia uma vez só (são fixos durante a execução)."""
    return CAMINHO_PROMPT.read_text(encoding="utf-8"), CAMINHO_GUIA_CALOR.read_text(encoding="utf-8")


def _numero(valor: float, casas: int = 1) -> str:
    """Formata com vírgula decimal, como o idoso está acostumado a ler: 34,2."""
    return f"{valor:.{casas}f}".replace(".", ",")
