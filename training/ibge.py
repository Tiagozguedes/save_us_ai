# Baixa e lê os dados do IBGE (Censo 2022) dos distritos de São Paulo; usado por build_dataset.py.
#
# Duas fontes, ambas públicas no FTP do IBGE:
#   1. Agregados por distrito, tema demografia (CSV dentro de um ZIP): moradores por faixa de idade.
#   2. Malha de distritos de SP com atributos (GeoPackage): o polígono de cada distrito, do qual
#      tiramos o centroide para consultar o clima.
# O GeoPackage é lido com sqlite3 da biblioteca padrão, sem GDAL, para não pesar o requirements.

from __future__ import annotations

import io
import sqlite3
import struct
import zipfile
from pathlib import Path

import httpx
import pandas as pd

from app.config import CODIGO_MUNICIPIO_SP, IBGE_VAR_POPULACAO, IBGE_VARS_60_MAIS

# Downloads grandes (o GeoPackage de SP tem ~19 MB); timeout generoso só no treino.
TIMEOUT_DOWNLOAD_S = 300


def baixar(url: str, destino: Path) -> Path:
    """Baixa url para destino, se o arquivo ainda não existir (cache em data/raw).

    Erros:
        httpx.HTTPError se o download falhar. Não há plano B: sem o dado oficial, o
        treino para (regra do projeto: não inventar dados).
    """
    if destino.exists():
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", url, timeout=TIMEOUT_DOWNLOAD_S, follow_redirects=True) as resposta:
        resposta.raise_for_status()
        temporario = destino.with_suffix(destino.suffix + ".parcial")
        with temporario.open("wb") as arquivo:
            for bloco in resposta.iter_bytes():
                arquivo.write(bloco)
    temporario.replace(destino)
    return destino


def ler_demografia_sp(caminho_zip: Path) -> pd.DataFrame:
    """Lê o ZIP de demografia por distrito e devolve os distritos de São Paulo.

    Retorno:
        DataFrame com codigo_ibge, populacao e pct_60_mais (0 a 100).

    Erros:
        ValueError se o arquivo não tiver as colunas esperadas.
    """
    with zipfile.ZipFile(caminho_zip) as pacote:
        nome_csv = next(n for n in pacote.namelist() if n.lower().endswith(".csv"))
        conteudo = pacote.read(nome_csv)

    # O IBGE publica em ISO-8859-1 com ";" e todos os campos entre aspas.
    tabela = pd.read_csv(io.BytesIO(conteudo), sep=";", encoding="latin-1", dtype=str)
    colunas = ["CD_DIST", IBGE_VAR_POPULACAO, *IBGE_VARS_60_MAIS]
    faltando = set(colunas) - set(tabela.columns)
    if faltando:
        raise ValueError(f"Arquivo do IBGE sem as colunas {sorted(faltando)}")

    sp = tabela[tabela["CD_DIST"].str.startswith(CODIGO_MUNICIPIO_SP)].copy()
    numeros = sp[[IBGE_VAR_POPULACAO, *IBGE_VARS_60_MAIS]].apply(pd.to_numeric, errors="raise")
    idosos = numeros[list(IBGE_VARS_60_MAIS)].sum(axis=1)

    return pd.DataFrame(
        {
            "codigo_ibge": sp["CD_DIST"],
            "populacao": numeros[IBGE_VAR_POPULACAO].astype(int),
            "pct_60_mais": (100 * idosos / numeros[IBGE_VAR_POPULACAO]).round(2),
            "idosos": idosos.astype(int),
        }
    ).reset_index(drop=True)


def ler_centroides_sp(caminho_gpkg: Path) -> pd.DataFrame:
    """Lê a malha de distritos e devolve nome e centroide de cada distrito de São Paulo.

    O nome vem da malha (UTF-8) e não do CSV de demografia, cujo latin-1 às vezes chega
    com acentos quebrados. A malha está em SIRGAS 2000 (EPSG:4674), que na prática coincide
    com o WGS 84 usado pelo Open-Meteo.

    Retorno:
        DataFrame com codigo_ibge, bairro, latitude e longitude.
    """
    with sqlite3.connect(caminho_gpkg) as banco:
        tabela, coluna_geo = banco.execute(
            "SELECT table_name, column_name FROM gpkg_geometry_columns LIMIT 1"
        ).fetchone()
        linhas = banco.execute(
            f'SELECT CD_DIST, NM_DIST, "{coluna_geo}" FROM "{tabela}" WHERE CD_DIST LIKE ?',
            (f"{CODIGO_MUNICIPIO_SP}%",),
        ).fetchall()

    registros = []
    for codigo, nome, blob in linhas:
        longitude, latitude = centroide(_poligonos_do_gpkg(blob))
        registros.append({"codigo_ibge": codigo, "bairro": nome, "latitude": round(latitude, 5), "longitude": round(longitude, 5)})
    return pd.DataFrame(registros)


# --- Geometria ---------------------------------------------------------------

Anel = list[tuple[float, float]]


def centroide(poligonos: list[list[Anel]]) -> tuple[float, float]:
    """Centroide (x, y) ponderado por área de um ou mais polígonos.

    Usa só o anel externo de cada polígono: distritos não têm buracos relevantes.
    Conta plana em graus; para áreas do tamanho de um distrito o erro é desprezível.
    """
    area_total = cx = cy = 0.0
    for aneis in poligonos:
        area, x, y = _area_e_centroide(aneis[0])
        area_total += area
        cx += x * area
        cy += y * area
    if area_total == 0:
        raise ValueError("Polígono sem área")
    return cx / area_total, cy / area_total


def _area_e_centroide(anel: Anel) -> tuple[float, float, float]:
    """Fórmula do laço (shoelace): área absoluta e centroide de um anel fechado."""
    soma_a = soma_x = soma_y = 0.0
    for (x0, y0), (x1, y1) in zip(anel, anel[1:]):
        cruz = x0 * y1 - x1 * y0
        soma_a += cruz
        soma_x += (x0 + x1) * cruz
        soma_y += (y0 + y1) * cruz
    area = soma_a / 2
    if area == 0:
        return 0.0, 0.0, 0.0
    return abs(area), soma_x / (6 * area), soma_y / (6 * area)


# Tamanho do envelope no cabeçalho do GeoPackage, pelo código dos bits 1-3 das flags.
_TAMANHO_ENVELOPE = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
_WKB_POLIGONO = 3
_WKB_MULTIPOLIGONO = 6


def _poligonos_do_gpkg(blob: bytes) -> list[list[Anel]]:
    """Converte a geometria binária do GeoPackage (cabeçalho GP + WKB) em polígonos."""
    if blob[:2] != b"GP":
        raise ValueError("Geometria fora do padrão GeoPackage")
    flags = blob[3]
    inicio_wkb = 8 + _TAMANHO_ENVELOPE[(flags >> 1) & 0b111]
    poligonos, _ = _ler_wkb(blob, inicio_wkb)
    return poligonos


def _ler_wkb(dados: bytes, pos: int) -> tuple[list[list[Anel]], int]:
    ordem = "<" if dados[pos] == 1 else ">"
    (tipo,) = struct.unpack_from(ordem + "I", dados, pos + 1)
    pos += 5
    tipo %= 1000  # ignora variantes Z/M (1003, 2003...), só x e y importam

    if tipo == _WKB_POLIGONO:
        aneis, pos = _ler_aneis(dados, pos, ordem)
        return [aneis], pos
    if tipo == _WKB_MULTIPOLIGONO:
        (quantidade,) = struct.unpack_from(ordem + "I", dados, pos)
        pos += 4
        poligonos = []
        for _ in range(quantidade):
            parte, pos = _ler_wkb(dados, pos)
            poligonos.extend(parte)
        return poligonos, pos
    raise ValueError(f"Tipo de geometria WKB não suportado: {tipo}")


def _ler_aneis(dados: bytes, pos: int, ordem: str) -> tuple[list[Anel], int]:
    (n_aneis,) = struct.unpack_from(ordem + "I", dados, pos)
    pos += 4
    aneis = []
    for _ in range(n_aneis):
        (n_pontos,) = struct.unpack_from(ordem + "I", dados, pos)
        pos += 4
        valores = struct.unpack_from(ordem + "d" * (2 * n_pontos), dados, pos)
        pos += 16 * n_pontos
        aneis.append(list(zip(valores[0::2], valores[1::2])))
    return aneis, pos
