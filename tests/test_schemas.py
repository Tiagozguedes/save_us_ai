# Testa as regras de validação dos contratos em app/schemas.py.

import pytest
from pydantic import ValidationError

from app.schemas import AlertaRequest


def test_aceita_so_o_bairro():
    pedido = AlertaRequest(bairro="Penha")

    assert pedido.clima_simulado is False


def test_aceita_clima_simulado_completo():
    pedido = AlertaRequest(bairro="Penha", temperatura_c=40, umidade_pct=30)

    assert pedido.clima_simulado is True


def test_recusa_temperatura_em_texto():
    with pytest.raises(ValidationError) as erro:
        AlertaRequest(bairro="Penha", temperatura_c="muito quente", umidade_pct=30)

    assert erro.value.errors()[0]["loc"] == ("temperatura_c",)


@pytest.mark.parametrize("campos", [{"temperatura_c": 40}, {"umidade_pct": 30}])
def test_recusa_clima_simulado_pela_metade(campos):
    with pytest.raises(ValidationError, match="juntos"):
        AlertaRequest(bairro="Penha", **campos)


@pytest.mark.parametrize("campos", [{"temperatura_c": 80, "umidade_pct": 30}, {"temperatura_c": 30, "umidade_pct": 120}])
def test_recusa_valores_fora_da_faixa(campos):
    with pytest.raises(ValidationError):
        AlertaRequest(bairro="Penha", **campos)


def test_recusa_bairro_vazio_e_campo_desconhecido():
    with pytest.raises(ValidationError):
        AlertaRequest(bairro="")
    with pytest.raises(ValidationError):
        AlertaRequest(bairro="Penha", nome_do_idoso="Maria")
