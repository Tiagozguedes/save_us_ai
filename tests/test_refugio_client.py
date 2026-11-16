# Testa o cliente da API .NET (app/services/refugio_client.py) com respostas HTTP simuladas.

import httpx
import pytest
import respx

from app.config import carregar_config
from app.services.refugio_client import RefugioClient, RefugioIndisponivel

URL = "http://api-net.teste"
CONFIG = carregar_config({"REFUGIO_API_URL": URL, "REFUGIO_API_EMAIL": "servico@email.com", "REFUGIO_API_SENHA": "x"})

# Formato real de RefugioResponse no .NET (camelCase).
BIBLIOTECA = {
    "id": 1, "nome": "Biblioteca Municipal da Penha", "tipo": "BIBLIOTECA", "cep": "03601-000",
    "endereco": "Rua Exemplo, 100", "bairro": "Penha", "capacidade": 20, "vagasDisponiveis": 18,
    "abre": "08:00", "fecha": "20:00", "acessivel": True, "ativo": True,
}


def pagina(*itens):
    return {"itens": list(itens), "pagina": 1, "tamanho": 10, "totalItens": len(itens), "totalPaginas": 1}


@pytest.fixture
def api():
    with respx.mock(base_url=URL, assert_all_called=False) as mock:
        yield mock


@pytest.fixture
def esperas():
    return []


@pytest.fixture
def cliente(esperas):
    return RefugioClient(CONFIG, http=httpx.Client(base_url=URL), dormir=esperas.append)


def test_faz_login_e_lista_refugios_ativos(api, cliente):
    login = api.post("/auth/login").respond(200, json={"token": "t1"})
    listagem = api.get("/api/v1/refugios").respond(200, json=pagina(BIBLIOTECA))

    refugios = cliente.listar_ativos("Penha")

    assert [(r.id, r.nome, r.vagas_disponiveis) for r in refugios] == [(1, "Biblioteca Municipal da Penha", 18)]
    assert login.calls.last.request.read() == b'{"email":"servico@email.com","senha":"x"}'
    pedido = listagem.calls.last.request
    assert pedido.headers["Authorization"] == "Bearer t1"
    assert pedido.url.params["bairro"] == "Penha"
    assert pedido.url.params["ativo"] == "true"


def test_reaproveita_o_token_entre_chamadas(api, cliente):
    login = api.post("/auth/login").respond(200, json={"token": "t1"})
    api.get("/api/v1/refugios").respond(200, json=pagina())

    cliente.listar_ativos("Penha")
    cliente.listar_ativos("Itaquera")

    assert login.call_count == 1


def test_ignora_refugio_inativo_que_escape_do_filtro(api, cliente):
    api.post("/auth/login").respond(200, json={"token": "t1"})
    api.get("/api/v1/refugios").respond(200, json=pagina(BIBLIOTECA, {**BIBLIOTECA, "id": 2, "ativo": False}))

    assert [r.id for r in cliente.listar_ativos("Penha")] == [1]


def test_refaz_login_ao_receber_401(api, cliente):
    login = api.post("/auth/login")
    login.side_effect = [httpx.Response(200, json={"token": "velho"}), httpx.Response(200, json={"token": "novo"})]
    listagem = api.get("/api/v1/refugios")
    listagem.side_effect = [httpx.Response(401), httpx.Response(200, json=pagina(BIBLIOTECA))]

    refugios = cliente.listar_ativos("Penha")

    assert len(refugios) == 1
    assert login.call_count == 2
    assert listagem.calls.last.request.headers["Authorization"] == "Bearer novo"


def test_401_depois_do_novo_login_vira_indisponivel(api, cliente):
    api.post("/auth/login").respond(200, json={"token": "t"})
    api.get("/api/v1/refugios").respond(401)

    with pytest.raises(RefugioIndisponivel, match="401"):
        cliente.listar_ativos("Penha")


def test_espera_retry_after_curto_e_tenta_de_novo(api, cliente, esperas):
    api.post("/auth/login").respond(200, json={"token": "t"})
    listagem = api.get("/api/v1/refugios")
    listagem.side_effect = [httpx.Response(429, headers={"Retry-After": "2"}), httpx.Response(200, json=pagina())]

    assert cliente.listar_ativos("Penha") == []
    assert esperas == [2.0]


def test_desiste_quando_retry_after_e_longo(api, cliente, esperas):
    api.post("/auth/login").respond(200, json={"token": "t"})
    api.get("/api/v1/refugios").respond(429, headers={"Retry-After": "60"})

    with pytest.raises(RefugioIndisponivel, match="60"):
        cliente.listar_ativos("Penha")
    assert esperas == []


def test_api_fora_do_ar_vira_indisponivel(api, cliente):
    api.post("/auth/login").mock(side_effect=httpx.ConnectError("recusada"))

    with pytest.raises(RefugioIndisponivel, match="ConnectError"):
        cliente.listar_ativos("Penha")


def test_timeout_vira_indisponivel(api, cliente):
    api.post("/auth/login").respond(200, json={"token": "t"})
    api.get("/api/v1/refugios").mock(side_effect=httpx.ReadTimeout("lento"))

    with pytest.raises(RefugioIndisponivel, match="ReadTimeout"):
        cliente.listar_ativos("Penha")


def test_login_recusado_vira_indisponivel(api, cliente):
    api.post("/auth/login").respond(401)

    with pytest.raises(RefugioIndisponivel, match="/auth/login respondeu 401"):
        cliente.listar_ativos("Penha")


def test_resposta_sem_itens_vira_indisponivel(api, cliente):
    api.post("/auth/login").respond(200, json={"token": "t"})
    api.get("/api/v1/refugios").respond(200, json={"outra": "coisa"})

    with pytest.raises(RefugioIndisponivel, match="formato inesperado"):
        cliente.listar_ativos("Penha")


def test_sem_credenciais_nem_chama_a_api(api):
    login = api.post("/auth/login").respond(200, json={"token": "t"})
    cliente = RefugioClient(carregar_config({"REFUGIO_API_URL": URL}), http=httpx.Client(base_url=URL))

    with pytest.raises(RefugioIndisponivel, match="não estão definidos"):
        cliente.listar_ativos("Penha")
    assert login.call_count == 0
