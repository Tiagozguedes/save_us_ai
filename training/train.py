# Treina, avalia e salva o classificador de risco. Rodar com: python -m training.train
#
# Compara três abordagens no mesmo teste (ano de 2025, nunca visto no treino):
#   1. Baseline: regra só pela temperatura do ar (training/baseline.py).
#   2. Regressão logística: linear, interpretável, mas não representa bem o índice de calor,
#      que é uma função não linear de temperatura e umidade.
#   3. Random Forest: captura a interação temperatura × umidade. É o modelo servido.
# Hiperparâmetros da RF escolhidos por validação cruzada por ano (treina 2023, valida 2024 e
# vice-versa), para que a escolha também respeite o tempo.
#
# Saídas: models/modelo_risco.joblib (RF + metadados) e models/metricas.json.

from __future__ import annotations

import json
from datetime import date

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.model_selection import GridSearchCV, GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.config import CAMINHO_DATASET, CAMINHO_MODELO, FEATURES, INICIO_TESTE, NIVEIS_RISCO, SEMENTE
from training.baseline import RegraTemperatura

CAMINHO_METRICAS = CAMINHO_MODELO.parent / "metricas.json"

# Grade pequena de propósito: o rótulo é uma regra suave e o ganho de buscar mais é pequeno.
# min_samples_leaf alto também deixa o arquivo do modelo leve.
GRADE_RF = {"max_depth": [6, 10, None], "min_samples_leaf": [5, 20, 50]}
ARVORES_RF = 200


def dividir_por_tempo(dataset: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separa treino (antes de INICIO_TESTE) e teste (a partir dele)."""
    treino = dataset[dataset["data"] < INICIO_TESTE]
    teste = dataset[dataset["data"] >= INICIO_TESTE]
    return treino, teste


def treinar_rf(x: pd.DataFrame, y: pd.Series, anos: pd.Series) -> GridSearchCV:
    """Ajusta a Random Forest com busca de hiperparâmetros validada por ano."""
    busca = GridSearchCV(
        RandomForestClassifier(n_estimators=ARVORES_RF, class_weight="balanced", random_state=SEMENTE, n_jobs=-1),
        GRADE_RF,
        scoring="f1_macro",
        cv=GroupKFold(n_splits=anos.nunique()),
        n_jobs=1,
    )
    busca.fit(x, y, groups=anos)
    return busca


def treinar_logistica(x: pd.DataFrame, y: pd.Series):
    """Ajusta a regressão logística com padronização das entradas."""
    modelo = make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=1000))
    return modelo.fit(x, y)


def avaliar(nome: str, y_real: pd.Series, y_previsto: np.ndarray) -> dict:
    """Calcula macro-F1, matriz de confusão e relatório por classe."""
    rotulos = list(NIVEIS_RISCO)
    return {
        "modelo": nome,
        "macro_f1": round(f1_score(y_real, y_previsto, average="macro", labels=rotulos), 4),
        # Linhas = classe real, colunas = classe prevista, na ordem baixo, medio, alto.
        "matriz_confusao": confusion_matrix(y_real, y_previsto, labels=rotulos).tolist(),
        "por_classe": {
            classe: {k: round(v, 4) for k, v in valores.items()}
            for classe, valores in classification_report(y_real, y_previsto, labels=rotulos, output_dict=True).items()
            if classe in rotulos
        },
    }


def main() -> None:
    """Treina os três modelos, imprime a comparação e salva a RF e as métricas."""
    dataset = pd.read_csv(CAMINHO_DATASET, dtype={"codigo_ibge": str})
    treino, teste = dividir_por_tempo(dataset)
    colunas = list(FEATURES)
    x_treino, y_treino = treino[colunas], treino["risco"]
    x_teste, y_teste = teste[colunas], teste["risco"]
    print(f"Treino: {len(treino)} linhas ({treino['data'].min()} a {treino['data'].max()})")
    print(f"Teste:  {len(teste)} linhas ({teste['data'].min()} a {teste['data'].max()})")

    baseline = RegraTemperatura().fit(treino["temperatura_c"].to_numpy(), y_treino.to_numpy())
    logistica = treinar_logistica(x_treino, y_treino)
    busca_rf = treinar_rf(x_treino, y_treino, treino["data"].str[:4])
    rf = busca_rf.best_estimator_

    resultados = [
        avaliar("baseline_temperatura", y_teste, baseline.predict(teste["temperatura_c"].to_numpy())),
        avaliar("regressao_logistica", y_teste, logistica.predict(x_teste)),
        avaliar("random_forest", y_teste, rf.predict(x_teste)),
    ]
    for r in resultados:
        print(f"  {r['modelo']:<22} macro-F1 = {r['macro_f1']:.4f}")

    metricas = {
        "treinado_em": date.today().isoformat(),
        "versao_sklearn": sklearn.__version__,
        "features": colunas,
        "classes": list(NIVEIS_RISCO),
        "linhas_treino": len(treino),
        "linhas_teste": len(teste),
        "distribuicao_teste": teste["risco"].value_counts().reindex(NIVEIS_RISCO).astype(int).to_dict(),
        "baseline_limites_c": {"medio": baseline.limite_medio_c, "alto": baseline.limite_alto_c},
        "rf_melhores_parametros": busca_rf.best_params_,
        "rf_macro_f1_validacao": round(busca_rf.best_score_, 4),
        "rf_importancia_features": dict(zip(colunas, np.round(rf.feature_importances_, 4).tolist())),
        "logistica_coeficientes": {
            classe: dict(zip(colunas, np.round(coefs, 4).tolist()))
            for classe, coefs in zip(logistica[-1].classes_, logistica[-1].coef_)
        },
        "resultados_teste": resultados,
    }

    CAMINHO_MODELO.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {"modelo": rf, "features": colunas, "classes": list(rf.classes_), "versao_sklearn": sklearn.__version__},
        CAMINHO_MODELO,
        compress=3,
    )
    CAMINHO_METRICAS.write_text(json.dumps(metricas, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Modelo salvo em {CAMINHO_MODELO.relative_to(CAMINHO_MODELO.parents[1])}")
    print(f"Métricas salvas em {CAMINHO_METRICAS.relative_to(CAMINHO_MODELO.parents[1])}")


if __name__ == "__main__":
    main()
