# Testa a leitura do .env em app/config.py.

import pytest

from app.config import carregar_config


def test_usa_padroes_quando_variaveis_faltam():
    config = carregar_config({})

    assert config.refugio_api_url == "https://refugio-api-gs.eastus.cloudapp.azure.com"
    assert config.refugio_api_timeout_s == 5
    assert config.llm_timeout_s == 15
    assert config.clima_timeout_s == 8
    assert config.refugio_credenciais_definidas is False


def test_le_variaveis_e_remove_barra_final_da_url():
    config = carregar_config(
        {
            "REFUGIO_API_URL": "http://localhost:5000/",
            "REFUGIO_API_EMAIL": "servico@email.com",
            "REFUGIO_API_SENHA": "segredo",
            "LLM_PROVIDER": "Ollama",
            "LLM_TIMEOUT_S": "2.5",
        }
    )

    assert config.refugio_api_url == "http://localhost:5000"
    assert config.refugio_credenciais_definidas is True
    assert config.llm_provider == "ollama"
    assert config.llm_timeout_s == 2.5


def test_valor_de_exemplo_nao_conta_como_credencial():
    config = carregar_config({"REFUGIO_API_EMAIL": "troque_aqui", "REFUGIO_API_SENHA": "troque_aqui"})

    assert config.refugio_credenciais_definidas is False


@pytest.mark.parametrize("valor", ["abc", "0", "-3"])
def test_timeout_invalido_gera_erro_claro(valor):
    with pytest.raises(ValueError, match="LLM_TIMEOUT_S"):
        carregar_config({"LLM_TIMEOUT_S": valor})
