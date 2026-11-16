# Texto padrão do alerta por nível de risco; usado por llm.py quando o LLM falha ou erra.
#
# Por que existe: o LLM pode estar fora do ar, demorar demais ou escrever algo fora das regras.
# O idoso não pode ficar sem aviso por isso. Estes textos são fixos, revisados pelo grupo e
# passam pela mesma validação do texto do LLM (ver tests/test_llm.py).

from __future__ import annotations

from app.config import TELEFONE_SAMU


def texto_padrao(risco: str, bairro: str, refugios: list[str]) -> str:
    """Monta o alerta fixo do nível de risco.

    Parâmetros:
        risco: 'baixo', 'medio' ou 'alto'.
        bairro: nome canônico do bairro.
        refugios: nomes dos refúgios com vaga (já filtrados e limitados por alerta.py).
            Vazio quando a API .NET não respondeu ou o bairro não tem refúgio aberto.

    Retorno:
        Texto curto, em linguagem simples, nunca vazio.
    """
    # "Aviso para Penha:" evita errar o artigo ("na Penha", "no Tatuapé") sem saber o gênero do nome.
    inicio = f"Aviso para {bairro}:"
    samu = f"Se passar mal, ligue {TELEFONE_SAMU}."

    if risco == "alto":
        lugar = f"Um lugar fresco e aberto perto de você: {refugios[0]}." if refugios else "Fique em um lugar fresco e com sombra."
        return f"{inicio} hoje o calor está perigoso. {lugar} Beba água várias vezes, mesmo sem sede. {samu}"

    if risco == "medio":
        lugar = f" Se precisar de um lugar fresco: {refugios[0]}." if refugios else ""
        return f"{inicio} hoje vai fazer calor. Beba água várias vezes e evite o sol entre 10h e 16h.{lugar} {samu}"

    return f"{inicio} hoje o dia está tranquilo. Lembre de beber água ao longo do dia."
