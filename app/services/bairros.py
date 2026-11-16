# Catálogo dos bairros que o modelo conhece (data/processed/bairros.csv); usado por alerta.py e main.py.
#
# Por que normalizar: o usuário pode digitar "tatuape" ou "PENHA". A busca aqui ignora acentos e
# maiúsculas e devolve o nome canônico ("Tatuapé"). É esse nome que vai para a API .NET, cujo
# filtro ignora maiúsculas mas NÃO ignora acentos.

from __future__ import annotations

import csv
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from app.config import CAMINHO_BAIRROS


@dataclass(frozen=True)
class Bairro:
    """Um distrito de São Paulo com o que o serviço precisa para o alerta."""

    codigo_ibge: str
    nome: str
    latitude: float
    longitude: float
    pct_60_mais: float


class CatalogoBairros:
    """Bairros indexados pelo nome normalizado."""

    def __init__(self, bairros: list[Bairro]) -> None:
        self._por_chave = {normalizar(b.nome): b for b in bairros}

    @classmethod
    def do_csv(cls, caminho: Path = CAMINHO_BAIRROS) -> "CatalogoBairros":
        """Lê o bairros.csv gerado por training/build_dataset.py.

        Erros:
            FileNotFoundError se o arquivo não existir; KeyError se faltar coluna.
        """
        with caminho.open(encoding="utf-8", newline="") as arquivo:
            bairros = [
                Bairro(
                    codigo_ibge=linha["codigo_ibge"],
                    nome=linha["bairro"],
                    latitude=float(linha["latitude"]),
                    longitude=float(linha["longitude"]),
                    pct_60_mais=float(linha["pct_60_mais"]),
                )
                for linha in csv.DictReader(arquivo)
            ]
        return cls(bairros)

    def buscar(self, nome: str) -> Bairro | None:
        """Devolve o bairro pelo nome, sem diferenciar acento nem maiúscula, ou None."""
        return self._por_chave.get(normalizar(nome))

    def nomes(self) -> list[str]:
        """Nomes canônicos em ordem alfabética (ignorando acentos)."""
        return [b.nome for _, b in sorted(self._por_chave.items())]


def normalizar(texto: str) -> str:
    """Tira acentos, espaços extras e maiúsculas: 'Tatuapé ' e 'tatuape' viram 'tatuape'."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return " ".join(sem_acento.lower().split())
