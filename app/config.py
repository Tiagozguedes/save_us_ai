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

# --- Dados de bairro (IBGE, Censo 2022) -------------------------------------

# "Bairro" no serviço = distrito do IBGE. Em São Paulo os 96 distritos têm os mesmos nomes
# usados no cadastro de refúgios da API .NET (Penha, Vila Matilde, Itaquera, Tatuapé).
CAMINHO_BAIRROS = PASTA_DADOS_PROCESSADOS / "bairros.csv"
CAMINHO_DATASET = PASTA_DADOS_PROCESSADOS / "dataset.csv"
CODIGO_MUNICIPIO_SP = "3550308"
_IBGE_AGREGADOS = "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios"
IBGE_DEMOGRAFIA_DISTRITOS_URL = f"{_IBGE_AGREGADOS}/Agregados_por_Distrito_csv/Agregados_por_distritos_demografia_BR.zip"
IBGE_MALHA_DISTRITOS_SP_URL = f"{_IBGE_AGREGADOS}/malha_com_atributos/distritos/gpkg/UF/SP/SP_distritos_CD2022.gpkg"
# Variáveis do dicionário de dados do IBGE (aba "Dicionário não PCT").
IBGE_VAR_POPULACAO = "V01006"  # Quantidade de moradores
IBGE_VARS_60_MAIS = ("V01040", "V01041")  # 60 a 69 anos, 70 anos ou mais

# --- Clima (Open-Meteo) -----------------------------------------------------

OPEN_METEO_PREVISAO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_HISTORICO_URL = "https://archive-api.open-meteo.com/v1/archive"
# Dias e horas sempre no horário de São Paulo, o mesmo fuso que a API .NET usa para as vagas.
FUSO_HORARIO = "America/Sao_Paulo"

# Histórico do treino: três anos completos, com as ondas de calor de 2023 e 2024.
HISTORICO_INICIO = "2023-01-01"
HISTORICO_FIM = "2025-12-31"
# ERA5-Land é a reanálise de maior resolução do Open-Meteo (grade de 0,1°, ~11 km). Vários
# distritos caem na mesma célula; baixamos uma vez por célula para respeitar o limite
# gratuito do Open-Meteo (pedir os 96 distritos um a um passaria do limite por hora).
HISTORICO_MODELO = "era5_land"
HISTORICO_GRADE_GRAUS = 0.1

# --- Rótulo de risco (derivado, não observado) ------------------------------
#
# Não existe dado público de "risco de calor por bairro". O rótulo é calculado por regra:
#   índice ajustado = índice de calor da pior hora
#                     + PESO_IDOSOS_C_POR_PP × (% de 60+ do bairro − % de 60+ da cidade)
# e comparado com as faixas da NOAA. O modelo aprende essa regra; a métrica mede
# consistência com ela, não acerto no mundo real (ver docs/avaliacao.md).

# Faixas da NOAA: "Caution" começa em 80 °F (26,7 °C) e "Extreme caution" em 90 °F (32,2 °C).
# Para idoso, "Extreme caution" já é risco alto: é onde a NOAA cita insolação como possível.
LIMIAR_RISCO_MEDIO_C = 26.7
LIMIAR_RISCO_ALTO_C = 32.2
# Cada ponto percentual de idosos acima da média da cidade soma 0,2 °C ao índice. Um bairro
# 10 p.p. mais idoso que a cidade sobe 2 °C, o que muda a faixa em dias de fronteira sem
# tornar a proporção de idosos mais importante que o próprio calor.
PESO_IDOSOS_C_POR_PP = 0.2

# --- Treino -----------------------------------------------------------------

# Entradas do modelo, nesta ordem. O índice de calor NÃO entra: o modelo precisa aprender a
# relação não linear entre temperatura e umidade, e é isso que separa RF de regressão logística.
FEATURES = ("temperatura_c", "umidade_pct", "pct_60_mais")
# Divisão por tempo: treina em 2023-2024 e testa em 2025. Dividir ao acaso colocaria o mesmo
# dia (de distritos vizinhos, com clima quase igual) no treino e no teste.
INICIO_TESTE = "2025-01-01"
SEMENTE = 42

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
