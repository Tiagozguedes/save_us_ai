# Testa o catálogo de bairros (app/services/bairros.py) e a carga do modelo (app/services/risco.py).

import joblib
import pandas as pd
import pytest
from sklearn.tree import DecisionTreeClassifier

from app.config import CAMINHO_MODELO
from app.services.bairros import CatalogoBairros, normalizar
from app.services.risco import ModeloIndisponivel, ModeloRisco

# Nomes cadastrados no seed da API .NET: precisam existir exatamente assim no catálogo.
BAIRROS_DO_NET = ["Penha", "Vila Matilde", "Itaquera", "Tatuapé"]


@pytest.fixture(scope="module")
def catalogo():
    return CatalogoBairros.do_csv()


# --- Bairros -----------------------------------------------------------------


def test_catalogo_tem_os_96_distritos_e_os_bairros_do_net(catalogo):
    nomes = catalogo.nomes()

    assert len(nomes) == 96
    assert set(BAIRROS_DO_NET) <= set(nomes)


@pytest.mark.parametrize("digitado", ["tatuape", "TATUAPÉ", "  Tatuapé  "])
def test_busca_ignora_acento_maiuscula_e_espaco(catalogo, digitado):
    assert catalogo.buscar(digitado).nome == "Tatuapé"


def test_bairro_desconhecido_devolve_none(catalogo):
    assert catalogo.buscar("BairroQueNaoExiste") is None


def test_normalizar_junta_espacos_internos():
    assert normalizar("Vila   Matilde") == "vila matilde"


# --- Modelo ------------------------------------------------------------------


@pytest.fixture
def modelo_pequeno(tmp_path):
    """Árvore treinada em poucos pontos, só para testar a carga sem depender do treino real."""
    x = pd.DataFrame(
        {"temperatura_c": [20, 22, 29, 30, 36, 38], "umidade_pct": [60] * 6, "pct_60_mais": [18] * 6}
    )
    y = ["baixo", "baixo", "medio", "medio", "alto", "alto"]
    caminho = tmp_path / "modelo.joblib"
    joblib.dump({"modelo": DecisionTreeClassifier().fit(x, y), "features": list(x.columns)}, caminho)
    return ModeloRisco(caminho)


def test_classifica_e_devolve_as_tres_probabilidades(modelo_pequeno):
    resultado = modelo_pequeno.classificar(37, 60, 18)

    assert resultado.risco == "alto"
    assert set(resultado.probabilidades) == {"baixo", "medio", "alto"}
    assert sum(resultado.probabilidades.values()) == pytest.approx(1)


def test_sem_arquivo_fica_nao_carregado_e_explica(tmp_path):
    modelo = ModeloRisco(tmp_path / "nao_existe.joblib")

    assert modelo.carregado is False
    assert "training.train" in modelo.erro
    with pytest.raises(ModeloIndisponivel):
        modelo.classificar(30, 50, 18)


def test_arquivo_corrompido_fica_nao_carregado(tmp_path):
    caminho = tmp_path / "ruim.joblib"
    caminho.write_bytes(b"isto nao e um modelo")

    assert ModeloRisco(caminho).carregado is False


@pytest.mark.skipif(not CAMINHO_MODELO.exists(), reason="modelo real não treinado (python -m training.train)")
@pytest.mark.parametrize("temperatura, umidade, esperado", [(40, 30, "alto"), (22, 60, "baixo")])
def test_modelo_real_nos_cenarios_do_readme(catalogo, temperatura, umidade, esperado):
    penha = catalogo.buscar("Penha")

    assert ModeloRisco().classificar(temperatura, umidade, penha.pct_60_mais).risco == esperado
