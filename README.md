# Refúgio IA — alertas de onda de calor para idosos

Global Solution 2026/2 · CitizenTech · FIAP · Disruptive Architectures: IoT, IoB & Generative IA

## Integrantes

| Nome | RM |
|---|---|
| Anna Clara Russo Luca | 561928 |
| Gabriel Duarte Maciel | 565754 |
| Tiago Guedes da Costa | 564731 |
| Gustavo Tavares da Silva | 562827 |

---

## O que é

O **Refúgio** é uma solução para proteger idosos durante ondas de calor. Prédios públicos e locais da comunidade (bibliotecas, UBSs, centros comunitários) funcionam como **refúgios climáticos**: o idoso reserva uma vaga pelo app e mostra o comprovante na porta.

Este repositório é o **módulo de IA** do projeto. Ele é um serviço em Python que:

1. **Prevê o risco de calor por bairro** (baixo, médio ou alto) com um modelo de Machine Learning, a partir de temperatura, umidade e proporção de pessoas com 60 anos ou mais.
2. **Gera um alerta personalizado e acessível** com um LLM: frases curtas, linguagem simples, o refúgio aberto no bairro e o que fazer.

O módulo consulta a **API .NET do Refúgio** para saber quais refúgios estão ativos no bairro. O app mobile consome só a API .NET, e este serviço é independente dele.

**Cidadão beneficiado:** idosos, principalmente os que moram sozinhos.
**ODS:** 3 (Saúde e bem-estar), 11 (Cidades e comunidades sustentáveis) e 13 (Ação contra a mudança global do clima).

## Objetivo

Antecipar o risco de calor em cada bairro e transformar esse dado em uma mensagem que o idoso entenda e possa seguir, apontando um refúgio onde há vaga.

- **Dentro do escopo:** classificar o risco por bairro, escrever o alerta, citar só refúgios reais devolvidos pela API .NET e continuar respondendo quando o LLM ou a API falham.
- **Fora do escopo:** diagnóstico médico, previsão meteorológica própria e envio do alerta ao celular (push, SMS).

## Como funciona

```mermaid
flowchart LR
    U[Cliente / Postman] -->|POST /alerta| API[Serviço FastAPI]
    API --> CLIMA[Open-Meteo<br/>temperatura e umidade]
    API --> ML[Modelo de risco<br/>scikit-learn]
    ML --> RISCO{Risco por bairro}
    API -->|GET /api/v1/refugios| NET[API .NET<br/>Refúgio]
    RISCO --> LLM[LLM<br/>gera o alerta]
    NET --> LLM
    GUIA[Guia do calor<br/>texto fixo] --> LLM
    LLM --> OUT[Alerta em linguagem simples]
    LLM -. falha ou timeout .-> FB[Texto padrão por nível de risco]
    FB --> OUT
```

1. O serviço obtém temperatura e umidade do bairro (Open-Meteo) ou usa os valores simulados enviados na requisição.
2. O modelo de ML classifica o risco com temperatura, umidade e % de idosos do bairro.
3. O serviço pede à API .NET os refúgios ativos no bairro.
4. O LLM recebe risco, números, refúgios e o Guia do calor, e escreve o alerta.
5. Se o LLM falhar, o serviço devolve um texto padrão para aquele nível de risco. O alerta nunca fica vazio.

**Dado pessoal:** nenhum dado do idoso (nome, telefone, contato de emergência) é enviado ao LLM. Ele recebe só bairro, risco, números do clima e nomes de refúgios.

## Tecnologias utilizadas

| Camada | Tecnologia | Para quê |
|---|---|---|
| Linguagem | Python 3.11+ | Todo o módulo de IA |
| API | FastAPI + Uvicorn | Endpoints `/alerta`, `/bairros`, `/health` e Swagger em `/docs` |
| Machine Learning | scikit-learn, pandas, joblib | Treino, avaliação e carga do classificador de risco |
| IA generativa | `[A DEFINIR: provedor e modelo — API ou Ollama local]` | Redação do alerta |
| Clima | Open-Meteo | Temperatura e umidade por latitude e longitude |
| Demografia | IBGE, Censo 2022 | Proporção de população com 60 anos ou mais por bairro |
| Integração | httpx | Chamadas à API .NET do Refúgio |
| Testes | pytest | Testes do modelo, do serviço e dos cenários de falha |
| Configuração | python-dotenv | Variáveis de ambiente (`.env`, fora do Git) |

### Modelo de ML

- **Tipo:** classificação em 3 classes (baixo, médio, alto).
- **Entradas:** temperatura (°C), umidade relativa (%) e % da população com 60 anos ou mais.
- **Algoritmo:** `[A DEFINIR: Random Forest ou Regressão Logística]`, comparado com um baseline por regra de temperatura.
- **Métricas:** macro-F1 e matriz de confusão (ver `docs/avaliacao.md`).

### Limitações

- **O rótulo de risco é derivado, não observado.** Não existe dado público de risco de calor por bairro. O rótulo vem do índice de calor combinado com a proporção de idosos. O modelo aprende essa regra, então uma métrica alta não prova acerto no mundo real. O que as métricas medem aqui é a consistência com a regra.
- O modelo não leva em conta ilha de calor urbana, condições de moradia nem saúde individual.
- O LLM pode errar ou escrever texto fora do padrão. Por isso o serviço valida a resposta (tamanho, refúgios citados) e tem texto padrão de reserva.
- O alerta não substitui orientação médica. Em sinais graves, o texto manda ligar para o SAMU (192).
- O serviço não tem autenticação na versão de demonstração.

## Como fazer funcionar

### Pré-requisitos

- Python 3.11 ou superior
- A API .NET do Refúgio acessível (publicada ou local). Se estiver na VM da Azure, ligue antes: `az vm start -g rg-refugio-api -n vm-refugio-api` (leva cerca de um minuto)
- Chave do provedor de LLM (ou Ollama instalado)

### Passo a passo

```bash
# 1. Clonar e entrar na pasta
git clone <URL-DO-REPOSITORIO>
cd <PASTA-DO-REPOSITORIO>

# 2. Ambiente virtual e dependências
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Configuração (nunca versione o .env)
cp .env.example .env             # Windows: copy .env.example .env
# edite o .env com a URL da API .NET, usuário de serviço e chave do LLM

# 4. Preparar os dados e treinar o modelo
python -m training.build_dataset
python -m training.train

# 5. Subir o serviço
uvicorn app.main:app --reload --port 8000
# Swagger: http://localhost:8000/docs

# 6. Rodar os testes
pytest -v
```

### Variáveis de ambiente (`.env.example`)

```env
# API .NET do Refúgio
REFUGIO_API_URL=https://refugio-api-gs.eastus.cloudapp.azure.com
# Conta de serviço do tipo IDOSO (somente leitura de refúgios).
# Crie uma conta própria via POST /auth/registrar; não use contas reais.
REFUGIO_API_EMAIL=troque_aqui
REFUGIO_API_SENHA=troque_aqui
REFUGIO_API_TIMEOUT_S=5

# LLM
LLM_PROVIDER=troque_aqui
LLM_API_KEY=troque_aqui
LLM_MODEL=troque_aqui
LLM_TIMEOUT_S=15

# Serviço
CLIMA_TIMEOUT_S=8
```

### Estrutura do repositório

```
app/
  main.py               rotas FastAPI
  config.py             leitura do .env
  schemas.py            contratos de entrada e saída
  services/
    clima.py            Open-Meteo
    refugio_client.py   login e consulta na API .NET
    risco.py            carrega o modelo e classifica
    llm.py              chamada ao LLM e validação do texto
    alerta.py           orquestra o fluxo completo
  prompts/alerta.txt    prompt do LLM
  content/guia_calor.txt
training/
  build_dataset.py      baixa e junta clima, IBGE e rótulos
  train.py              treina, avalia e salva o modelo
data/                   dados brutos e processados
models/                 modelo treinado (.joblib)
tests/                  testes pytest
docs/avaliacao.md       métricas, casos de teste e análise
```

---

## Fluxo de uso por endpoints (Postman)

### Preparação

Crie duas variáveis de coleção:

| Variável | Valor |
|---|---|
| `baseUrl` | `https://refugio-api-gs.eastus.cloudapp.azure.com` (API .NET) |
| `iaUrl` | `http://localhost:8000` (serviço de IA) |

Em todas as requisições com corpo, use o header `Content-Type: application/json`.

### 1. Serviço de IA está no ar

```
GET {{iaUrl}}/health
```

Esperado: `200`. Confira se `modelo_carregado` é `true`.

### 2. Login na API .NET (para conferir os refúgios)

```
POST {{baseUrl}}/auth/login
```

```json
{
  "email": "maria@email.com",
  "senha": "Senha@123"
}
```

Na aba **Tests** do Postman, para guardar o token:

```javascript
pm.collectionVariables.set("tokenIdoso", pm.response.json().token);
```

Esperado: `200` com o campo `token`.

### 3. Ver os refúgios ativos no bairro (API .NET)

```
GET {{baseUrl}}/api/v1/refugios?bairro=Penha&ativo=true&pagina=1&tamanho=10
Authorization: Bearer {{tokenIdoso}}
```

Esperado: `200`. Anote os nomes: o alerta do passo 6 só pode citar refúgios desta lista.

### 4. Bairros suportados pelo modelo

```
GET {{iaUrl}}/bairros
```

Esperado: `200` com a lista de bairros que o modelo conhece, no formato `{ "bairros": ["Itaquera", "Penha", ...] }`.

### 5. Alerta com o clima real do dia

```
POST {{iaUrl}}/alerta
```

```json
{
  "bairro": "Penha"
}
```

Esperado: `200`, com o formato abaixo (valores ilustrativos).

```json
{
  "bairro": "Penha",
  "temperatura_c": 34.2,
  "umidade_pct": 48,
  "indice_calor_c": 37.5,
  "risco": "alto",
  "probabilidades": { "baixo": 0.03, "medio": 0.17, "alto": 0.80 },
  "refugios": [{ "id": 1, "nome": "Biblioteca Municipal da Penha", "vagas_disponiveis": 18 }],
  "refugios_consultados": true,
  "alerta": "Hoje vai fazer muito calor na Penha. Vá para a Biblioteca Municipal da Penha, onde é fresco. Beba água. Se passar mal, ligue 192.",
  "origem_texto": "llm"
}
```

### 6. Alerta simulando calor extremo

Os campos `temperatura_c` e `umidade_pct` são opcionais e substituem o clima real. Servem para demonstrar e testar, e vêm juntos: mandar só um deles devolve `422`.

```
POST {{iaUrl}}/alerta
```

```json
{
  "bairro": "Penha",
  "temperatura_c": 40,
  "umidade_pct": 30
}
```

Esperado: `200`, `risco: "alto"` e o SAMU (192) no texto.

### 7. Alerta simulando dia ameno

```
POST {{iaUrl}}/alerta
```

```json
{
  "bairro": "Penha",
  "temperatura_c": 22,
  "umidade_pct": 60
}
```

Esperado: `200`, `risco: "baixo"` e texto sem tom de alarme.

### 8. Falhas (cenários de teste)

**Bairro inexistente**

```
POST {{iaUrl}}/alerta
```

```json
{
  "bairro": "BairroQueNaoExiste"
}
```

Esperado: `404` com mensagem clara.

**Corpo inválido**

```
POST {{iaUrl}}/alerta
```

```json
{
  "bairro": "Penha",
  "temperatura_c": "muito quente"
}
```

Esperado: `422` com o campo inválido apontado.

**API .NET fora do ar:** desligue a VM da Azure (`az vm deallocate -g rg-refugio-api -n vm-refugio-api`) e repita o passo 6. Esperado: `200`, `refugios_consultados: false` e um alerta sem refúgio específico.

**LLM indisponível:** coloque uma chave inválida no `.env`, reinicie o serviço e repita o passo 6. Esperado: `200`, `origem_texto: "fallback"` e o texto padrão do nível de risco.

---

## Uso de IA generativa

`[A PREENCHER PELO GRUPO — o edital pede esta declaração]`

| Ferramenta | Para que foi usada |
|---|---|
| `[ferramenta]` | `[ex.: apoio no planejamento, explicação de erros, revisão de texto]` |

Todo código e texto gerado por IA foi lido, testado e revisado pelo grupo.

## Fontes de dados

- Open-Meteo: https://open-meteo.com
- IBGE, Censo Demográfico 2022: https://www.ibge.gov.br
- Índice de calor: fórmula da NOAA (Rothfusz)
