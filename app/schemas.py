# Contratos de entrada e saída da API FastAPI (os formatos descritos no README).
# Usado por main.py nas rotas e por alerta.py para montar a resposta.

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Risco = Literal["baixo", "medio", "alto"]
OrigemTexto = Literal["llm", "fallback"]

# Faixas aceitas na simulação. Fora delas o número é erro de digitação, não clima de São Paulo,
# e o modelo nunca viu nada parecido no treino.
TEMPERATURA_MIN_C = -10.0
TEMPERATURA_MAX_C = 55.0


class AlertaRequest(BaseModel):
    """Corpo de POST /alerta.

    temperatura_c e umidade_pct são opcionais e substituem o clima real do Open-Meteo.
    Servem para demonstração e teste, por isso vêm juntos ou não vêm.
    """

    model_config = ConfigDict(extra="forbid")

    bairro: str = Field(min_length=1, max_length=100, examples=["Penha"])
    temperatura_c: float | None = Field(default=None, ge=TEMPERATURA_MIN_C, le=TEMPERATURA_MAX_C, examples=[40])
    umidade_pct: float | None = Field(default=None, ge=0, le=100, examples=[30])

    @model_validator(mode="after")
    def _clima_simulado_completo(self) -> "AlertaRequest":
        if (self.temperatura_c is None) != (self.umidade_pct is None):
            raise ValueError("Envie temperatura_c e umidade_pct juntos, ou nenhum dos dois para usar o clima real.")
        return self

    @property
    def clima_simulado(self) -> bool:
        """True quando a requisição trouxe temperatura e umidade."""
        return self.temperatura_c is not None


class Probabilidades(BaseModel):
    """Probabilidade que o modelo dá a cada nível de risco (soma 1)."""

    baixo: float
    medio: float
    alto: float


class RefugioResumo(BaseModel):
    """Refúgio ativo devolvido pela API .NET, só com o que o alerta precisa."""

    id: int
    nome: str
    vagas_disponiveis: int


class AlertaResponse(BaseModel):
    """Resposta de POST /alerta."""

    bairro: str
    temperatura_c: float
    umidade_pct: float
    indice_calor_c: float
    risco: Risco
    probabilidades: Probabilidades
    refugios: list[RefugioResumo]
    # False quando a API .NET não respondeu: o alerta sai sem refúgio específico.
    refugios_consultados: bool
    alerta: str
    origem_texto: OrigemTexto


class BairrosResponse(BaseModel):
    """Resposta de GET /bairros: os bairros que o modelo conhece."""

    bairros: list[str]


class HealthResponse(BaseModel):
    """Resposta de GET /health."""

    status: Literal["ok"] = "ok"
    modelo_carregado: bool
