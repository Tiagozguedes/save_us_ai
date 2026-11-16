# Cenários de falha do README (seção 8) e outros que o serviço precisa aguentar sem deixar o
# idoso sem alerta. Regra geral: só bairro desconhecido (404), entrada inválida (422) e falta
# de modelo ou de clima (503) impedem o alerta; o resto sai com 200 e texto de reserva.

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.config import carregar_config
from app.main import criar_app
from app.services.alerta import ServicoAlerta
from app.services.bairros import CatalogoBairros
from app.services.clima import ClimaIndisponivel
from app.services.llm import LLMIndisponivel, OllamaLLM
from app.services.refugio_client import RefugioClient, RefugioIndisponivel
from app.services.risco import ModeloRisco
from app.services.texto_padrao import texto_padrao
from tests.conftest import LOTADO, LLMFalso, ModeloFalso, RefugiosFalsos, clima_fixo

CALOR_EXTREMO = {"bairro": "Penha", "temperatura_c": 40, "umidade_pct": 30}


def montar_cliente(modelo=None, refugios=None, llm=None, obter_clima=None, config=None):
    servico = ServicoAlerta(
        config or carregar_config({}),
        CatalogoBairros.do_csv(),
        modelo or ModeloFalso(),
        refugios,
        llm,
        obter_clima=obter_clima or clima_fixo(),
    )
    return TestClient(criar_app(servico))


# --- API .NET ----------------------------------------------------------------


def test_api_net_fora_do_ar_devolve_alerta_sem_refugio(pecas, cliente):
    pecas["refugios"].erro = RefugioIndisponivel("VM desligada")

    corpo = cliente.post("/alerta", json=CALOR_EXTREMO).json()

    assert corpo["refugios_consultados"] is False
    assert corpo["refugios"] == []
    assert "192" in corpo["alerta"]
    # O LLM falso cita "CEU Penha"; sem lista da API, a validação recusa e usa o texto padrão.
    assert "CEU" not in corpo["alerta"]
    assert corpo["origem_texto"] == "fallback"
    assert "(lista indisponível agora)" in pecas["llm"].prompts[-1]


def test_bairro_sem_refugio_aberto(pecas, cliente):
    pecas["refugios"].refugios = []

    corpo = cliente.post("/alerta", json=CALOR_EXTREMO).json()

    assert corpo["refugios_consultados"] is True
    assert corpo["refugios"] == []
    assert "(nenhum refúgio aberto com vaga hoje)" in pecas["llm"].prompts[-1]


def test_refugios_lotados_nao_entram_no_alerta(pecas, cliente):
    pecas["refugios"].refugios = [LOTADO]

    corpo = cliente.post("/alerta", json=CALOR_EXTREMO).json()

    assert corpo["refugios"] == []
    assert LOTADO.nome not in corpo["alerta"]


URL_NET = "http://api-net.teste"
CONFIG_NET = carregar_config({"REFUGIO_API_URL": URL_NET, "REFUGIO_API_EMAIL": "servico@email.com", "REFUGIO_API_SENHA": "x"})


@pytest.mark.parametrize(
    "falha",
    [
        httpx.ConnectError("conexão recusada"),  # VM desligada (az vm deallocate)
        httpx.ConnectTimeout("sem resposta"),
        httpx.Response(429, headers={"Retry-After": "60"}),
        httpx.Response(500),
    ],
)
def test_cliente_real_da_api_net_com_falha_nao_derruba_o_alerta(falha):
    with respx.mock(base_url=URL_NET) as api:
        rota = api.post("/auth/login")
        if isinstance(falha, Exception):
            rota.mock(side_effect=falha)
        else:
            rota.mock(return_value=falha)
        refugios = RefugioClient(CONFIG_NET, http=httpx.Client(base_url=URL_NET), dormir=lambda s: None)

        with montar_cliente(refugios=refugios, llm=LLMFalso()) as cliente:
            resposta = cliente.post("/alerta", json=CALOR_EXTREMO)

    assert resposta.status_code == 200
    assert resposta.json()["refugios_consultados"] is False


# --- LLM ---------------------------------------------------------------------


def test_llm_indisponivel_usa_texto_padrao(pecas, cliente):
    pecas["llm"].erro = LLMIndisponivel("Ollama desligado")

    corpo = cliente.post("/alerta", json=CALOR_EXTREMO).json()

    assert corpo["origem_texto"] == "fallback"
    assert corpo["alerta"] == texto_padrao("alto", "Penha", ["CEU Penha", "Biblioteca Municipal da Penha"])


def test_llm_que_inventa_refugio_usa_texto_padrao(pecas, cliente):
    pecas["llm"].resposta = "Hoje o calor está perigoso. Vá para o Shopping Penha. Se passar mal, ligue 192."

    corpo = cliente.post("/alerta", json=CALOR_EXTREMO).json()

    assert corpo["origem_texto"] == "fallback"
    assert "Shopping" not in corpo["alerta"]


def test_llm_sem_samu_no_risco_alto_usa_texto_padrao(pecas, cliente):
    pecas["llm"].resposta = "Hoje está quente. Vá para o CEU Penha e beba água."

    corpo = cliente.post("/alerta", json=CALOR_EXTREMO).json()

    assert corpo["origem_texto"] == "fallback"
    assert "192" in corpo["alerta"]


def test_ollama_real_com_timeout_usa_texto_padrao():
    config = carregar_config({"LLM_URL": "http://ollama.teste"})
    with respx.mock(base_url="http://ollama.teste") as ollama:
        ollama.post("/api/chat").mock(side_effect=httpx.ReadTimeout("lento"))
        llm = OllamaLLM(config, http=httpx.Client(base_url="http://ollama.teste"))

        with montar_cliente(refugios=RefugiosFalsos(), llm=llm) as cliente:
            corpo = cliente.post("/alerta", json=CALOR_EXTREMO).json()

    assert corpo["origem_texto"] == "fallback"


def test_api_net_e_llm_fora_do_ar_ao_mesmo_tempo():
    with montar_cliente(refugios=RefugiosFalsos(erro=RefugioIndisponivel("x")), llm=None) as cliente:
        resposta = cliente.post("/alerta", json=CALOR_EXTREMO)

    corpo = resposta.json()
    assert resposta.status_code == 200
    assert corpo["origem_texto"] == "fallback"
    assert corpo["alerta"] == texto_padrao("alto", "Penha", [])


# --- Clima e modelo ----------------------------------------------------------


def clima_fora_do_ar(latitude, longitude, config):
    raise ClimaIndisponivel("Open-Meteo falhou: ConnectTimeout")


def test_open_meteo_fora_do_ar_devolve_503_com_dica():
    with montar_cliente(refugios=RefugiosFalsos(), llm=LLMFalso(), obter_clima=clima_fora_do_ar) as cliente:
        resposta = cliente.post("/alerta", json={"bairro": "Penha"})

    assert resposta.status_code == 503
    assert "temperatura_c e umidade_pct" in resposta.json()["detail"]


def test_open_meteo_fora_do_ar_nao_afeta_clima_simulado():
    with montar_cliente(refugios=RefugiosFalsos(), llm=LLMFalso(), obter_clima=clima_fora_do_ar) as cliente:
        resposta = cliente.post("/alerta", json=CALOR_EXTREMO)

    assert resposta.status_code == 200


def test_sem_modelo_treinado_health_avisa_e_alerta_devolve_503(tmp_path):
    modelo = ModeloRisco(tmp_path / "nao_existe.joblib")

    with montar_cliente(modelo=modelo, refugios=RefugiosFalsos(), llm=LLMFalso()) as cliente:
        health = cliente.get("/health").json()
        resposta = cliente.post("/alerta", json=CALOR_EXTREMO)

    assert health["modelo_carregado"] is False
    assert resposta.status_code == 503
    assert "training.train" in resposta.json()["detail"]
