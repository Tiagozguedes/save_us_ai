# Monta os dados do projeto: baixa IBGE e Open-Meteo, junta por distrito e aplica o rótulo.
# Rodar com: python -m training.build_dataset   (depois: python -m training.train)
#
# Saídas em data/processed/:
#   bairros.csv  — 96 distritos de SP: código IBGE, nome, centroide, população e % de 60+.
#                  Também é lido pelo serviço em produção (coordenadas para o clima e % de 60+).
#   dataset.csv  — uma linha por distrito e dia (2023-2025) com o clima da pior hora e o risco.
# Downloads brutos ficam em data/raw/ (fora do Git) e servem de cache.

from __future__ import annotations

import pandas as pd

from app.config import (
    CAMINHO_BAIRROS,
    CAMINHO_DATASET,
    IBGE_DEMOGRAFIA_DISTRITOS_URL,
    IBGE_MALHA_DISTRITOS_SP_URL,
    PASTA_DADOS_BRUTOS,
)
from training.clima_historico import baixar_celula, celula, pior_hora_por_dia
from training.ibge import baixar, ler_centroides_sp, ler_demografia_sp
from training.rotulo import rotular_risco


def montar_bairros() -> tuple[pd.DataFrame, float]:
    """Junta demografia e centroides do IBGE em uma tabela de bairros.

    Retorno:
        (tabela de bairros, % de 60+ da cidade inteira).

    Erros:
        ValueError se algum distrito existir em só uma das fontes.
    """
    demografia = ler_demografia_sp(baixar(IBGE_DEMOGRAFIA_DISTRITOS_URL, PASTA_DADOS_BRUTOS / "ibge_demografia_distritos.zip"))
    centroides = ler_centroides_sp(baixar(IBGE_MALHA_DISTRITOS_SP_URL, PASTA_DADOS_BRUTOS / "SP_distritos_CD2022.gpkg"))

    bairros = centroides.merge(demografia, on="codigo_ibge", how="outer", indicator=True)
    sem_par = bairros[bairros["_merge"] != "both"]
    if not sem_par.empty:
        raise ValueError(f"Distritos sem par entre demografia e malha: {sem_par['codigo_ibge'].tolist()}")

    # Média da cidade ponderada pela população, e não média simples dos distritos.
    pct_cidade = round(100 * bairros["idosos"].sum() / bairros["populacao"].sum(), 2)
    bairros = bairros.drop(columns=["_merge", "idosos"]).sort_values("bairro").reset_index(drop=True)
    return bairros, pct_cidade


def montar_dataset(bairros: pd.DataFrame, pct_cidade: float) -> pd.DataFrame:
    """Cruza cada bairro com o clima diário da sua célula e calcula o rótulo de risco."""
    bairros = bairros.copy()
    bairros[["cel_lat", "cel_lon"]] = [celula(la, lo) for la, lo in zip(bairros["latitude"], bairros["longitude"])]

    partes = []
    celulas = bairros[["cel_lat", "cel_lon"]].drop_duplicates().itertuples(index=False)
    for lat, lon in celulas:
        print(f"  clima da célula {lat:.2f}, {lon:.2f}")
        diario = pior_hora_por_dia(baixar_celula(lat, lon, PASTA_DADOS_BRUTOS / "clima"))
        diario["cel_lat"], diario["cel_lon"] = lat, lon
        partes.append(diario)
    clima = pd.concat(partes, ignore_index=True)

    dataset = bairros.merge(clima, on=["cel_lat", "cel_lon"], how="inner")
    dataset["risco"] = [
        rotular_risco(ic, pct, pct_cidade) for ic, pct in zip(dataset["indice_calor_c"], dataset["pct_60_mais"])
    ]
    colunas = ["codigo_ibge", "bairro", "data", "temperatura_c", "umidade_pct", "pct_60_mais", "indice_calor_c", "risco"]
    return dataset[colunas].sort_values(["data", "bairro"]).reset_index(drop=True)


def main() -> None:
    """Gera bairros.csv e dataset.csv e mostra um resumo das classes."""
    print("Lendo IBGE (Censo 2022)...")
    bairros, pct_cidade = montar_bairros()
    CAMINHO_BAIRROS.parent.mkdir(parents=True, exist_ok=True)
    bairros.to_csv(CAMINHO_BAIRROS, index=False, encoding="utf-8")
    print(f"  {len(bairros)} bairros; % de 60+ na cidade: {pct_cidade}")

    print("Lendo Open-Meteo (histórico ERA5-Land)...")
    dataset = montar_dataset(bairros, pct_cidade)
    dataset.to_csv(CAMINHO_DATASET, index=False, encoding="utf-8")

    print(f"Dataset: {len(dataset)} linhas, de {dataset['data'].min()} a {dataset['data'].max()}")
    print(dataset["risco"].value_counts(normalize=True).round(3).to_string())


if __name__ == "__main__":
    main()
