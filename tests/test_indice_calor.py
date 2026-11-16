# Confere app/services/indice_calor.py contra a tabela de índice de calor da NOAA/NWS.

import pytest

from app.services.indice_calor import indice_calor_c


def f_para_c(f):
    return (f - 32) * 5 / 9


# (temperatura °F, umidade %, índice da tabela NWS em °F)
TABELA_NWS = [
    (80, 40, 80),
    (90, 70, 106),
    (96, 50, 108),
    (100, 40, 109),
    (86, 90, 105),
]


@pytest.mark.parametrize("temp_f, umidade, esperado_f", TABELA_NWS)
def test_bate_com_a_tabela_da_nws(temp_f, umidade, esperado_f):
    # A tabela publicada arredonda para o grau inteiro em °F: tolerância de 1 °F (~0,6 °C).
    assert indice_calor_c(f_para_c(temp_f), umidade) == pytest.approx(f_para_c(esperado_f), abs=0.6)


def test_dia_ameno_fica_perto_da_temperatura():
    assert indice_calor_c(22, 60) == pytest.approx(22, abs=1)


def test_calor_umido_e_pior_que_calor_seco():
    assert indice_calor_c(34, 80) > indice_calor_c(34, 30)


@pytest.mark.parametrize("umidade", [-1, 101])
def test_recusa_umidade_fora_da_faixa(umidade):
    with pytest.raises(ValueError):
        indice_calor_c(30, umidade)
