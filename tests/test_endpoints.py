# Testa as rotas da API (app/main.py) no caminho feliz e nos erros de entrada (404 e 422).
# Segue os passos 1, 4, 5, 6, 7 e 8 do fluxo do Postman no README.

from tests.conftest import BIBLIOTECA, CEU


def test_health_mostra_modelo_carregado(cliente):
    resposta = cliente.get("/health")

    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok", "modelo_carregado": True}


def test_bairros_lista_os_96_distritos(cliente):
    bairros = cliente.get("/bairros").json()["bairros"]

    assert len(bairros) == 96
    assert {"Penha", "Tatuapé", "Itaquera", "Vila Matilde"} <= set(bairros)


def test_alerta_com_clima_real_tem_o_formato_do_readme(cliente, pecas):
    resposta = cliente.post("/alerta", json={"bairro": "Penha"})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert set(corpo) == {
        "bairro", "temperatura_c", "umidade_pct", "indice_calor_c", "risco", "probabilidades",
        "refugios", "refugios_consultados", "alerta", "origem_texto",
    }
    assert corpo["temperatura_c"] == 34.2 and corpo["umidade_pct"] == 48
    assert corpo["risco"] == "alto"
    assert set(corpo["probabilidades"]) == {"baixo", "medio", "alto"}
    assert corpo["refugios_consultados"] is True
    assert corpo["origem_texto"] == "llm"


def test_alerta_simulando_calor_extremo(cliente, pecas):
    corpo = cliente.post("/alerta", json={"bairro": "Penha", "temperatura_c": 40, "umidade_pct": 30}).json()

    assert corpo["risco"] == "alto"
    assert "192" in corpo["alerta"]
    # O índice de calor é recalculado a partir do clima simulado, não vem do Open-Meteo.
    assert corpo["indice_calor_c"] > 40
    assert pecas["modelo"].entradas[-1][:2] == (40, 30)


def test_alerta_simulando_dia_ameno(cliente, pecas):
    pecas["llm"].resposta = "Hoje o dia está tranquilo na Penha, com 22 graus. Lembre de beber água."

    corpo = cliente.post("/alerta", json={"bairro": "Penha", "temperatura_c": 22, "umidade_pct": 60}).json()

    assert corpo["risco"] == "baixo"
    assert corpo["origem_texto"] == "llm"
    assert "perigoso" not in corpo["alerta"]


def test_so_refugios_com_vaga_e_o_de_mais_vagas_primeiro(cliente):
    corpo = cliente.post("/alerta", json={"bairro": "Penha", "temperatura_c": 40, "umidade_pct": 30}).json()

    assert [r["id"] for r in corpo["refugios"]] == [CEU.id, BIBLIOTECA.id]


def test_bairro_digitado_sem_acento_vira_nome_canonico_na_api_net(cliente, pecas):
    corpo = cliente.post("/alerta", json={"bairro": "tatuape", "temperatura_c": 25, "umidade_pct": 50}).json()

    assert corpo["bairro"] == "Tatuapé"
    assert pecas["refugios"].bairros_pedidos == ["Tatuapé"]


def test_prompt_nao_leva_dado_pessoal_e_so_leva_refugios_com_vaga(cliente, pecas):
    cliente.post("/alerta", json={"bairro": "Penha", "temperatura_c": 40, "umidade_pct": 30})

    prompt = pecas["llm"].prompts[-1]
    assert "CEU Penha" in prompt and "Biblioteca Municipal da Penha" in prompt
    assert "UBS Lotada" not in prompt
    # Valores do perfil de teste da API .NET (nome, telefone, contato de emergência, e-mail).
    for dado_pessoal in ("Maria", "(11)", "João", "@"):
        assert dado_pessoal not in prompt


def test_bairro_inexistente_devolve_404(cliente):
    resposta = cliente.post("/alerta", json={"bairro": "BairroQueNaoExiste"})

    assert resposta.status_code == 404
    assert "GET /bairros" in resposta.json()["detail"]


def test_temperatura_em_texto_devolve_422_apontando_o_campo(cliente):
    resposta = cliente.post("/alerta", json={"bairro": "Penha", "temperatura_c": "muito quente"})

    assert resposta.status_code == 422
    assert resposta.json()["detail"][0]["loc"] == ["body", "temperatura_c"]


def test_campo_pessoal_no_corpo_devolve_422(cliente, pecas):
    resposta = cliente.post("/alerta", json={"bairro": "Penha", "nome": "Maria Souza"})

    assert resposta.status_code == 422
    assert pecas["llm"].prompts == []
