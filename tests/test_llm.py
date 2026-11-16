# Testa o texto do alerta: prompt, validação, cliente do Ollama e texto padrão
# (app/services/llm.py e app/services/texto_padrao.py). O LLM é sempre simulado aqui.

import dataclasses

import httpx
import pytest
import respx

from app.config import ALERTA_MAX_CARACTERES, carregar_config
from app.services.llm import (
    DadosAlerta,
    LLMIndisponivel,
    OllamaLLM,
    criar_llm,
    escrever_alerta,
    limpar,
    montar_prompt,
    motivo_invalido,
)
from app.services.texto_padrao import texto_padrao

BIBLIOTECA = "Biblioteca Municipal da Penha"
ALTO = DadosAlerta("Penha", "alto", 38.0, 35, 39.4, [BIBLIOTECA], True)
BAIXO = DadosAlerta("Penha", "baixo", 22.0, 60, 21.9, [BIBLIOTECA], True)
SEM_API = dataclasses.replace(ALTO, refugios=[], refugios_consultados=False)

BOM_ALTO = f"Hoje o calor está perigoso na Penha. Vá para a {BIBLIOTECA}, onde é fresco. Beba água. Se passar mal, ligue 192."


class LLMFixo:
    """LLM de teste que devolve sempre o mesmo texto (ou levanta erro)."""

    def __init__(self, resposta=None, erro=None):
        self.resposta, self.erro, self.prompts = resposta, erro, []

    def gerar(self, prompt):
        self.prompts.append(prompt)
        if self.erro:
            raise self.erro
        return self.resposta


# --- Prompt ------------------------------------------------------------------


def test_prompt_leva_dados_e_guia_sem_placeholder_sobrando():
    prompt = montar_prompt(ALTO)

    assert "Bairro: Penha" in prompt
    assert "Risco de calor hoje: alto" in prompt
    assert "38,0 °C" in prompt
    assert BIBLIOTECA in prompt
    assert "GUIA DO CALOR" in prompt
    assert "$" not in prompt


def test_prompt_avisa_quando_a_lista_de_refugios_nao_veio():
    assert "(lista indisponível agora)" in montar_prompt(SEM_API)


# --- Validação ---------------------------------------------------------------


def test_texto_bom_passa():
    assert motivo_invalido(BOM_ALTO, ALTO) is None


@pytest.mark.parametrize(
    "texto, trecho_do_motivo",
    [
        ("", "vazio"),
        ("a" * (ALERTA_MAX_CARACTERES + 1), "caracteres"),
        (f"Hoje está muito quente. Vá para a {BIBLIOTECA}. Beba água.", "SAMU"),
        (f"Vá para a {BIBLIOTECA} ou para o CEU Penha. Ligue 192.", "CEU"),
        (f"Vá para a {BIBLIOTECA} ou para a UBS do bairro. Ligue 192.", "ubs"),
        (f"Vá para a {BIBLIOTECA}, na Rua Exemplo, 100. Ligue 192.", "telefone ou endereço"),
        ("Hoje o calor está perigoso. Fique na sombra. Se passar mal, ligue 192.", "não cita nenhum"),
        (f"Vá para a {BIBLIOTECA}, que tem ar-condicionado. Ligue 192.", "não informa"),
        (f"Hoje o calor está perigoso na Vila Exemplo. Vá para a {BIBLIOTECA}. Ligue 192.", "exemplos"),
    ],
)
def test_texto_fora_das_regras_e_recusado(texto, trecho_do_motivo):
    assert trecho_do_motivo in motivo_invalido(texto, ALTO)


def test_sem_lista_da_api_nao_pode_citar_lugar():
    assert "biblioteca" in motivo_invalido(BOM_ALTO, SEM_API)


def test_ceu_minusculo_e_o_ceu_e_nao_o_equipamento():
    texto = "Dia tranquilo, de céu limpo. Lembre de beber água."

    assert motivo_invalido(texto, BAIXO) is None


def test_limpar_remove_marcacao_e_aspas():
    assert limpar('  "**Atenção:** beba   água."\n') == "Atenção: beba água."


# --- Fluxo com o LLM ---------------------------------------------------------


def test_usa_o_texto_do_llm_quando_valido():
    llm = LLMFixo(resposta=BOM_ALTO)

    texto, origem = escrever_alerta(llm, ALTO)

    assert (texto, origem) == (BOM_ALTO, "llm")


def test_texto_invalido_cai_no_padrao():
    texto, origem = escrever_alerta(LLMFixo(resposta="Vá ao Shopping Penha."), ALTO)

    assert origem == "fallback"
    assert "192" in texto


def test_llm_indisponivel_cai_no_padrao():
    texto, origem = escrever_alerta(LLMFixo(erro=LLMIndisponivel("fora do ar")), ALTO)

    assert origem == "fallback"
    assert texto == texto_padrao("alto", "Penha", [BIBLIOTECA])


def test_sem_provedor_usa_o_padrao():
    assert escrever_alerta(None, BAIXO)[1] == "fallback"


def test_provedor_desconhecido_nao_cria_cliente():
    assert criar_llm(carregar_config({"LLM_PROVIDER": "outro"})) is None


# --- Cliente do Ollama -------------------------------------------------------

CONFIG = carregar_config({"LLM_URL": "http://ollama.teste", "LLM_MODEL": "llama3.1"})


@pytest.fixture
def ollama():
    with respx.mock(base_url="http://ollama.teste", assert_all_called=False) as mock:
        yield mock.post("/api/chat")


def test_ollama_envia_modelo_sem_streaming_e_le_a_resposta(ollama):
    ollama.respond(200, json={"message": {"role": "assistant", "content": "Beba água."}})

    texto = OllamaLLM(CONFIG, http=httpx.Client(base_url="http://ollama.teste")).gerar("oi")

    corpo = ollama.calls.last.request.read().decode()
    assert texto == "Beba água."
    assert '"model":"llama3.1"' in corpo
    assert '"stream":false' in corpo


@pytest.mark.parametrize(
    "resposta",
    [httpx.ConnectError("recusada"), httpx.ReadTimeout("lento"), httpx.Response(404), httpx.Response(200, json={})],
)
def test_ollama_com_problema_vira_indisponivel(ollama, resposta):
    if isinstance(resposta, Exception):
        ollama.mock(side_effect=resposta)
    else:
        ollama.mock(return_value=resposta)

    with pytest.raises(LLMIndisponivel):
        OllamaLLM(CONFIG, http=httpx.Client(base_url="http://ollama.teste")).gerar("oi")


# --- Texto padrão ------------------------------------------------------------


@pytest.mark.parametrize("risco", ["baixo", "medio", "alto"])
@pytest.mark.parametrize("refugios, consultados", [([BIBLIOTECA], True), ([], True), ([], False)])
def test_texto_padrao_passa_na_propria_validacao(risco, refugios, consultados):
    dados = DadosAlerta("Penha", risco, 30.0, 50, 31.0, refugios, consultados)

    texto = texto_padrao(risco, "Penha", refugios)

    assert motivo_invalido(texto, dados) is None


def test_texto_padrao_baixo_nao_assusta():
    texto = texto_padrao("baixo", "Penha", [])

    assert "perigoso" not in texto and "192" not in texto
