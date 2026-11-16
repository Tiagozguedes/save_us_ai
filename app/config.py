# Lê o .env e reúne as constantes do serviço; usado por todos os módulos de app/ e training/.
#
# Regra do projeto: nenhum número solto no código. Limiares, tempos e caminhos ficam aqui,
# com o motivo de cada valor ao lado.

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv

# --- Caminhos ---------------------------------------------------------------

RAIZ = Path(__file__).resolve().parent.parent
PASTA_DADOS = RAIZ / "data"
PASTA_DADOS_BRUTOS = PASTA_DADOS / "raw"
PASTA_DADOS_PROCESSADOS = PASTA_DADOS / "processed"
CAMINHO_MODELO = RAIZ / "models" / "modelo_risco.joblib"
CAMINHO_PROMPT = RAIZ / "app" / "prompts" / "alerta.txt"
CAMINHO_GUIA_CALOR = RAIZ / "app" / "content" / "guia_calor.txt"

# --- Domínio ----------------------------------------------------------------

# Ordem fixa das classes: o modelo, as probabilidades e os textos padrão usam a mesma.
NIVEIS_RISCO = ("baixo", "medio", "alto")

# --- Clima (Open-Meteo) -----------------------------------------------------

OPEN_METEO_PREVISAO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_HISTORICO_URL = "https://archive-api.open-meteo.com/v1/archive"
# Dias e horas sempre no horário de São Paulo, o mesmo fuso que a API .NET usa para as vagas.
FUSO_HORARIO = "America/Sao_Paulo"

# --- Integração com a API .NET ----------------------------------------------

# Tamanho de página pedido à listagem. O máximo da API .NET é 50 e um bairro tem poucos
# refúgios, então uma página basta.
REFUGIOS_TAMANHO_PAGINA = 10

# Espera máxima aceita num 429. A API .NET manda Retry-After de até 60 s, mas o alerta
# não pode travar esse tempo todo: acima deste limite, desistimos e o alerta sai sem
# refúgio específico (refugios_consultados: false).
RETRY_AFTER_MAX_S = 5.0

# --- Validação do texto do LLM ----------------------------------------------

# Idoso lê melhor mensagem curta. 400 caracteres cabem em uma tela de celular com fonte grande.
ALERTA_MAX_CARACTERES = 400
TELEFONE_SAMU = "192"


@dataclass(frozen=True)
class Config:
    """Valores que mudam por ambiente e vêm do .env (ou de variáveis do sistema)."""

    refugio_api_url: str
    refugio_api_email: str
    refugio_api_senha: str
    # Timeout curto: a VM da Azure pode estar desligada e o alerta não deve esperar por ela.
    refugio_api_timeout_s: float
    llm_provider: str
    llm_api_key: str
    llm_model: str
    # O LLM é o passo mais lento; acima disso o serviço usa o texto padrão.
    llm_timeout_s: float
    clima_timeout_s: float

    @property
    def refugio_credenciais_definidas(self) -> bool:
        """Diz se e-mail e senha da conta de serviço foram preenchidos no .env."""
        return _preenchido(self.refugio_api_email) and _preenchido(self.refugio_api_senha)


# Valor que o .env.example traz como lembrete para o grupo trocar.
_VALOR_DE_EXEMPLO = "troque_aqui"

_PADROES = {
    "REFUGIO_API_URL": "https://refugio-api-gs.eastus.cloudapp.azure.com",
    "REFUGIO_API_TIMEOUT_S": "5",
    "LLM_TIMEOUT_S": "15",
    "CLIMA_TIMEOUT_S": "8",
}


def carregar_config(env: Mapping[str, str] | None = None) -> Config:
    """Monta a configuração a partir do ambiente.

    Parâmetros:
        env: variáveis a usar. Se for None, lê o .env da raiz e depois os.environ
            (os testes passam um dicionário para não depender da máquina).

    Retorno:
        Config preenchida. Campos de credencial ausentes viram texto vazio: o serviço
        sobe mesmo assim e trata a falta como falha da integração, sem derrubar o alerta.

    Erros:
        ValueError se um timeout não for número positivo.
    """
    if env is None:
        load_dotenv(RAIZ / ".env")
        env = os.environ

    def ler(nome: str) -> str:
        return env.get(nome, _PADROES.get(nome, "")).strip()

    return Config(
        refugio_api_url=ler("REFUGIO_API_URL").rstrip("/"),
        refugio_api_email=ler("REFUGIO_API_EMAIL"),
        refugio_api_senha=ler("REFUGIO_API_SENHA"),
        refugio_api_timeout_s=_ler_segundos(ler("REFUGIO_API_TIMEOUT_S"), "REFUGIO_API_TIMEOUT_S"),
        llm_provider=ler("LLM_PROVIDER").lower(),
        llm_api_key=ler("LLM_API_KEY"),
        llm_model=ler("LLM_MODEL"),
        llm_timeout_s=_ler_segundos(ler("LLM_TIMEOUT_S"), "LLM_TIMEOUT_S"),
        clima_timeout_s=_ler_segundos(ler("CLIMA_TIMEOUT_S"), "CLIMA_TIMEOUT_S"),
    )


def _ler_segundos(valor: str, nome: str) -> float:
    """Converte um timeout do .env em float positivo, com erro claro se estiver errado."""
    try:
        segundos = float(valor)
    except ValueError:
        raise ValueError(f"{nome} precisa ser um número de segundos, veio {valor!r}") from None
    if segundos <= 0:
        raise ValueError(f"{nome} precisa ser maior que zero, veio {segundos}")
    return segundos


def _preenchido(valor: str) -> bool:
    return bool(valor) and valor != _VALOR_DE_EXEMPLO
