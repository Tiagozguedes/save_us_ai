# CLAUDE.md — Refúgio IA

Instruções para o Claude Code neste repositório. Leia tudo antes de começar.

## Contexto

Este repositório é o **módulo de IA em Python** do projeto Refúgio (Global Solution 2026/2, FIAP, tema CitizenTech). O `README.md` é o **contrato do projeto**: endpoints, formatos de resposta, variáveis de ambiente e estrutura de pastas. Siga-o. Se precisar mudar algo, altere o código e o README na mesma branch.

O serviço (FastAPI):
1. Classifica o **risco de calor por bairro** (baixo, médio, alto) com um modelo de ML (scikit-learn), usando temperatura, umidade e % de população 60+.
2. Pede à **API .NET do Refúgio** os refúgios ativos no bairro.
3. Usa um **LLM** para escrever um alerta curto, em linguagem simples, citando só refúgios reais.
4. Se o LLM falhar, devolve um **texto padrão** por nível de risco.

Entrega: dia **19/11/2026, 23h55**, sem prorrogação. Vale pontuação: IA generativa funcionando (25), aprofundamento em ML justificado (25), dados e arquitetura documentados (15), testes e avaliação (15), organização e uso responsável (10), adequação (10).

## Projeto .NET (somente leitura)

A API .NET está em `https://github.com/Tiagozguedes/refugio_.net` (publicada em `https://refugio-api-gs.eastus.cloudapp.azure.com`). **Não altere nada nela.** Este serviço só a consome.

Rotas usadas:
- `POST /auth/login` com `{"email","senha"}`, devolve `token`.
- `GET /api/v1/refugios?bairro=&data=&ativo=&pagina=&tamanho=` com `Authorization: Bearer <token>`.

Cuidados na integração:
- Use uma conta de serviço do tipo **IDOSO** (o README do .NET mostra a listagem funcionando com token de idoso). Credenciais só no `.env`.
- **Antes de escrever o cliente**, leia os nomes reais dos campos de resposta da listagem no código do .NET (DTOs de refúgio) ou no `/swagger`. Não invente nomes de campo. Se não achar, pergunte ao usuário.
- Confira como o filtro de bairro compara texto (maiúsculas, acentos) e use nos dados do modelo os mesmos nomes de bairro do banco do .NET.
- Faça login de novo ao receber 401. Ao receber 429, espere o `Retry-After`. Use timeout curto.
- A VM da Azure pode estar desligada. Trate a falha sem derrubar o alerta: devolva-o sem refúgio específico e com `refugios_consultados: false`.

## Fluxo de Git (obrigatório)

### Branches
- `main` só recebe código que roda e passa nos testes. Nunca commite direto nela, exceto o commit inicial.
- **Uma branch por implementação**, saindo da `main` atualizada, com nome `tipo/descricao-curta` em minúsculas e com hífen: `feat/cliente-refugio-net`, `fix/timeout-llm`, `docs/readme-avaliacao`.
- Ao terminar, rode `pytest`, faça merge na `main` com `git merge --no-ff` (ou PR, se o grupo usar) e volte a trabalhar a partir da `main`.

### Commits
- **Frequentes e pequenos**: um commit por passo lógico (uma função, um teste, um ajuste). Prefira 10 commits pequenos a 1 grande.
- **Formato (Conventional Commits, em português):** `tipo(escopo): descrição no imperativo`
  - `feat(risco): adiciona classificador de risco por bairro`
  - `fix(llm): usa texto padrão quando a chamada expira`
  - `test(alerta): cobre bairro sem refúgio aberto`
  - `docs(readme): atualiza passo a passo do Postman`
- Tipos: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `style`, `perf`.
- Primeira linha com até 72 caracteres, sem ponto final. Use o corpo do commit para explicar o **porquê** quando não for óbvio.
- Nunca commite `.env`, chaves, senhas, `.venv`, `__pycache__`. Mantenha o `.gitignore` correto desde o primeiro commit.
- O histórico de Git faz parte da avaliação do grupo: mensagens claras, sem commits como "ajustes" ou "wip".

### Plano de branches (nesta ordem)
1. `chore/estrutura-inicial`: pastas, `requirements.txt`, `.gitignore`, `.env.example`
2. `feat/config-e-schemas`: leitura do `.env` e contratos de entrada e saída
3. `feat/cliente-refugio-net`: login, listagem, 401 e 429
4. `feat/clima-open-meteo`: temperatura e umidade por bairro
5. `feat/dataset-e-treino`: dados, rótulo de risco, treino e avaliação
6. `feat/servico-risco`: carga do modelo e classificação
7. `feat/llm-alerta`: prompt, chamada ao LLM, validação do texto e fallback
8. `feat/endpoints-fastapi`: `/health`, `/bairros`, `/alerta`
9. `test/cenarios-de-falha`: testes dos cenários listados no README
10. `docs/avaliacao-e-readme`: `docs/avaliacao.md` e ajustes finais do README

## Comentários e legibilidade

O grupo inteiro precisa entender o código, inclusive quem não escreveu aquela parte.

- Escreva comentários e docstrings **em português**.
- Todo arquivo começa com um comentário curto dizendo **o que faz e onde se encaixa no fluxo** (ex.: "Chama a API .NET para listar refúgios; usado por alerta.py").
- Toda função pública tem docstring com: o que faz, parâmetros, retorno e o que acontece em caso de erro.
- Comente o **porquê**, não o óbvio. Decisões e limites merecem comentário: por que o rótulo é derivado, por que há texto padrão, por que o timeout vale tanto.
- Nomes de domínio em português (`refugio`, `bairro`, `risco`), nomes técnicos podem ficar em inglês (`client`, `timeout`).
- Funções curtas, um arquivo por responsabilidade, constantes e limiares em `config.py` (nada de números soltos no código).

## Regras de dados e IA

- **Não invente dados.** Proporção de idosos vem do Censo 2022 (IBGE), clima vem do Open-Meteo. Se não conseguir baixar, pare e avise o usuário, em vez de preencher com números fictícios.
- O **rótulo de risco é derivado** (índice de calor da NOAA combinado com % de idosos). Documente isso em código e em `docs/avaliacao.md`, e não apresente a métrica como acerto no mundo real.
- Compare o modelo com um **baseline** por regra simples. Reporte macro-F1 e matriz de confusão.
- **Nenhum dado pessoal** do idoso vai ao LLM: só bairro, risco, números do clima e nomes de refúgios.
- Valide o texto do LLM (tamanho máximo, só refúgios que vieram da API, SAMU 192 quando o risco for alto). Se a validação falhar, use o texto padrão.
- Decisões ainda abertas, **pergunte ao usuário antes de escolher**: provedor e modelo do LLM, algoritmo do ML (Random Forest ou regressão logística).

## Definição de pronto (por branch)

- O código roda e os testes da branch passam (`pytest -v`).
- Sem credenciais no diff (`git diff` revisado antes do commit).
- Comentários e docstrings no lugar.
- README atualizado se o contrato mudou.

## Final do projeto

- O README precisa da seção **Uso de IA generativa** preenchida pelo grupo (ferramentas e finalidade). Lembre o usuário disso ao final.
- A entrega no portal é **só um `.txt`** com RM, nome completo dos integrantes e o link do repositório no GitHub. Garanta que o repositório esteja público ou acessível ao professor.
