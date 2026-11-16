# Testa as peças de training/ que montam o dataset: rótulo, leitura do IBGE e clima histórico.

import io
import struct
import zipfile

import pytest

from app.config import LIMIAR_RISCO_ALTO_C, LIMIAR_RISCO_MEDIO_C
from training.clima_historico import celula, pior_hora_por_dia
from training.ibge import _poligonos_do_gpkg, centroide, ler_demografia_sp
from training.rotulo import indice_ajustado, rotular_risco

# --- Rótulo ------------------------------------------------------------------


@pytest.mark.parametrize(
    "indice, esperado",
    [(LIMIAR_RISCO_MEDIO_C - 0.1, "baixo"), (LIMIAR_RISCO_MEDIO_C, "medio"), (LIMIAR_RISCO_ALTO_C, "alto")],
)
def test_rotulo_segue_as_faixas_da_noaa_no_bairro_medio(indice, esperado):
    assert rotular_risco(indice, pct_60_mais=17.0, pct_60_mais_cidade=17.0) == esperado


def test_bairro_mais_idoso_sobe_de_faixa_no_mesmo_calor():
    indice = LIMIAR_RISCO_ALTO_C - 1.0

    assert rotular_risco(indice, pct_60_mais=17.0, pct_60_mais_cidade=17.0) == "medio"
    assert rotular_risco(indice, pct_60_mais=27.0, pct_60_mais_cidade=17.0) == "alto"


def test_ajuste_e_simetrico_em_torno_da_media_da_cidade():
    assert indice_ajustado(30, 22, 17) - 30 == pytest.approx(30 - indice_ajustado(30, 12, 17))


# --- IBGE --------------------------------------------------------------------


def test_centroide_de_um_quadrado():
    quadrado = [[(0, 0), (2, 0), (2, 2), (0, 2), (0, 0)]]

    assert centroide([quadrado]) == pytest.approx((1, 1))


def test_centroide_pondera_pela_area():
    pequeno = [[(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]]
    grande = [[(10, 0), (13, 0), (13, 3), (10, 3), (10, 0)]]

    x, _ = centroide([pequeno, grande])

    assert x == pytest.approx((0.5 * 1 + 11.5 * 9) / 10)


def test_le_poligono_do_geopackage():
    anel = [(0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (0.0, 2.0), (0.0, 0.0)]
    wkb = struct.pack("<BII", 1, 3, 1) + struct.pack("<I", len(anel)) + b"".join(struct.pack("<dd", *p) for p in anel)
    # Cabeçalho GP, versão 0, flags: little endian (bit 0) e envelope de 32 bytes (código 1).
    cabecalho = b"GP" + bytes([0, 0b0011]) + struct.pack("<i", 4674) + struct.pack("<4d", 0, 4, 0, 2)

    poligonos = _poligonos_do_gpkg(cabecalho + wkb)

    assert centroide(poligonos) == pytest.approx((2, 1))


def test_le_demografia_so_de_sao_paulo(tmp_path):
    # Estrutura igual à do arquivo do IBGE (latin-1, ";" e aspas); valores só para o teste.
    csv = (
        '"CD_DIST";"NM_DIST";"V01006";"V01040";"V01041"\n'
        '"355030859";"Penha";"1000";"120";"80"\n'
        '"330455705";"Rio de Janeiro";"500";"50";"50"\n'
    )
    caminho = tmp_path / "demografia.zip"
    with zipfile.ZipFile(caminho, "w") as pacote:
        pacote.writestr("demografia.csv", csv.encode("latin-1"))

    tabela = ler_demografia_sp(caminho)

    assert tabela.to_dict("records") == [{"codigo_ibge": "355030859", "populacao": 1000, "pct_60_mais": 20.0, "idosos": 200}]


def test_demografia_sem_coluna_esperada_falha(tmp_path):
    caminho = tmp_path / "demografia.zip"
    with zipfile.ZipFile(caminho, "w") as pacote:
        pacote.writestr("x.csv", '"CD_DIST";"V01006"\n"355030859";"10"\n')

    with pytest.raises(ValueError, match="V01040"):
        ler_demografia_sp(caminho)


# --- Clima histórico ---------------------------------------------------------


def test_celula_arredonda_para_a_grade_de_0_1_grau():
    assert celula(-23.5232, -46.5288) == (-23.5, -46.5)
    assert celula(-23.5562, -46.4558) == (-23.6, -46.5)


def test_pior_hora_por_dia_escolhe_uma_hora_por_dia():
    dados = {
        "hourly": {
            "time": ["2025-01-01T13:00", "2025-01-01T15:00", "2025-01-02T14:00"],
            "temperature_2m": [30.0, 33.0, None],
            "relative_humidity_2m": [60.0, 40.0, None],
        }
    }

    diario = pior_hora_por_dia(dados)

    # O dia 02 não tem dado e fica de fora.
    assert diario["data"].tolist() == ["2025-01-01"]
    assert diario.loc[0, "temperatura_c"] == 33.0
