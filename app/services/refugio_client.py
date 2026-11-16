# Chama a API .NET do Refúgio para listar os refúgios ativos de um bairro; usado por alerta.py.
#
# Nomes de campo conferidos no código do .NET (refugio_.net):
#   - LoginResponse: { token, expiraEm, usuario }
#   - PaginaResponse<RefugioResponse>: { itens, pagina, tamanho, totalItens, totalPaginas }
#   - RefugioResponse: { id, nome, tipo, cep, endereco, bairro, capacidade, vagasDisponiveis,
#                        abre, fecha, acessivel, ativo }
# O filtro ?bairro= da API compara com ToLower(): ignora maiúsculas, mas NÃO ignora acentos.
# Por isso o serviço sempre envia o nome canônico do bairro ("Tatuapé"), nunca o que o
# usuário digitou.

from __future__ import annotations

import threading
import time
from typing import Callable

import httpx

from app.config import REFUGIOS_TAMANHO_PAGINA, RETRY_AFTER_MAX_S, Config
from app.schemas import RefugioResumo

ROTA_LOGIN = "/auth/login"
ROTA_REFUGIOS = "/api/v1/refugios"


class RefugioIndisponivel(Exception):
    """A API .NET não respondeu ou respondeu algo inesperado.

    Quem chama (alerta.py) trata isso montando o alerta sem refúgio específico e com
    refugios_consultados: false. O alerta nunca cai por causa da API .NET.
    """


class RefugioClient:
    """Cliente da API .NET com login automático.

    Guarda o token da conta de serviço e o reaproveita entre chamadas. Ao receber 401
    (token expirado), faz login de novo uma vez. Ao receber 429, espera o Retry-After
    se ele for curto (até RETRY_AFTER_MAX_S) e tenta mais uma vez.
    """

    def __init__(
        self,
        config: Config,
        http: httpx.Client | None = None,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        """Parâmetros:
        config: URL, credenciais e timeout da API .NET.
        http: cliente httpx a usar; os testes passam um com transporte simulado.
        dormir: função de espera do 429; os testes trocam por uma que não espera.
        """
        self._config = config
        self._http = http or httpx.Client(base_url=config.refugio_api_url, timeout=config.refugio_api_timeout_s)
        self._dormir = dormir
        self._token: str | None = None
        # O FastAPI roda rotas síncronas em várias threads; o lock evita dois logins ao mesmo tempo.
        self._lock = threading.Lock()

    def listar_ativos(self, bairro: str) -> list[RefugioResumo]:
        """Lista os refúgios ativos do bairro, com as vagas de hoje.

        Parâmetros:
            bairro: nome canônico do bairro, igual ao cadastrado no banco do .NET.

        Retorno:
            Lista de RefugioResumo (pode ser vazia se o bairro não tem refúgio ativo).

        Erros:
            RefugioIndisponivel se faltar credencial, a API estiver fora do ar, expirar o
            timeout, o login falhar ou a resposta vier num formato diferente do esperado.
        """
        params = {"bairro": bairro, "ativo": "true", "pagina": 1, "tamanho": REFUGIOS_TAMANHO_PAGINA}
        resposta = self._get_autenticado(ROTA_REFUGIOS, params)
        return _ler_refugios(resposta)

    def fechar(self) -> None:
        """Fecha as conexões HTTP abertas."""
        self._http.close()

    # --- Internos ------------------------------------------------------------

    def _get_autenticado(self, rota: str, params: dict) -> httpx.Response:
        token = self._token_atual()
        resposta = self._enviar("GET", rota, params=params, headers=_bearer(token))

        if resposta.status_code == httpx.codes.UNAUTHORIZED:
            # Token expirou ou foi invalidado: um novo login e uma nova tentativa, só uma vez.
            token = self._token_atual(renovar=True)
            resposta = self._enviar("GET", rota, params=params, headers=_bearer(token))

        _exigir_sucesso(resposta, rota)
        return resposta

    def _token_atual(self, renovar: bool = False) -> str:
        with self._lock:
            if renovar or self._token is None:
                self._token = self._login()
            return self._token

    def _login(self) -> str:
        if not self._config.refugio_credenciais_definidas:
            raise RefugioIndisponivel("REFUGIO_API_EMAIL e REFUGIO_API_SENHA não estão definidos no .env")

        corpo = {"email": self._config.refugio_api_email, "senha": self._config.refugio_api_senha}
        resposta = self._enviar("POST", ROTA_LOGIN, json=corpo)
        _exigir_sucesso(resposta, ROTA_LOGIN)

        try:
            return resposta.json()["token"]
        except (ValueError, KeyError, TypeError):
            raise RefugioIndisponivel("Login respondeu sem o campo 'token'") from None

    def _enviar(self, metodo: str, rota: str, **kwargs) -> httpx.Response:
        """Faz a requisição e, num 429 com espera curta, espera e repete uma vez."""
        resposta = self._requisitar(metodo, rota, **kwargs)
        if resposta.status_code != httpx.codes.TOO_MANY_REQUESTS:
            return resposta

        espera = _segundos_retry_after(resposta)
        if espera is None or espera > RETRY_AFTER_MAX_S:
            raise RefugioIndisponivel(f"API .NET pediu para esperar {espera} s em {rota}; desistindo")
        self._dormir(espera)
        return self._requisitar(metodo, rota, **kwargs)

    def _requisitar(self, metodo: str, rota: str, **kwargs) -> httpx.Response:
        try:
            return self._http.request(metodo, rota, **kwargs)
        except httpx.HTTPError as erro:
            # Inclui timeout e conexão recusada (VM da Azure desligada).
            raise RefugioIndisponivel(f"Falha ao chamar {rota}: {type(erro).__name__}") from erro


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _exigir_sucesso(resposta: httpx.Response, rota: str) -> None:
    if not resposta.is_success:
        raise RefugioIndisponivel(f"{rota} respondeu {resposta.status_code}")


def _segundos_retry_after(resposta: httpx.Response) -> float | None:
    """Lê o Retry-After em segundos. A API .NET sempre manda número inteiro."""
    try:
        return float(resposta.headers["Retry-After"])
    except (KeyError, ValueError):
        return None


def _ler_refugios(resposta: httpx.Response) -> list[RefugioResumo]:
    try:
        itens = resposta.json()["itens"]
        return [
            RefugioResumo(id=item["id"], nome=item["nome"], vagas_disponiveis=item["vagasDisponiveis"])
            for item in itens
            # O filtro ativo=true já vem da API; conferimos de novo porque o alerta só pode citar refúgio aberto.
            if item.get("ativo", False)
        ]
    except (ValueError, KeyError, TypeError) as erro:
        raise RefugioIndisponivel(f"Listagem de refúgios em formato inesperado: {erro}") from None
