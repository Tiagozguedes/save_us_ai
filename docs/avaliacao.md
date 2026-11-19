# Avaliação — Refúgio IA

Métricas, casos de teste e análise do módulo de IA. Os números do modelo vêm de `models/metricas.json`, gerado por `python -m training.train` (scikit-learn 1.9.1, semente 42).

## 1. O que está sendo avaliado

1. **Modelo de ML:** classifica o risco de calor de um bairro em um dia (baixo, médio, alto) a partir de temperatura, umidade e % da população com 60 anos ou mais.
2. **IA generativa:** o texto do alerta escrito pelo LLM (Ollama, `llama3.1` 8B) e a validação que decide entre o texto do LLM e o texto padrão.
3. **Serviço:** as rotas e o comportamento quando a API .NET, o LLM, o Open-Meteo ou o modelo falham.

## 2. Dados

| Fonte | O que vem dela | Como |
|---|---|---|
| IBGE, Censo 2022, agregados por distrito (demografia) | População total (`V01006`) e de 60 anos ou mais (`V01040` + `V01041`) | ZIP no FTP do IBGE |
| IBGE, malha de distritos de SP com atributos (2022) | Polígono de cada distrito, de onde sai o centroide | GeoPackage no FTP do IBGE |
| Open-Meteo, histórico ERA5-Land | Temperatura e umidade horárias de 2023 a 2025 | API de arquivo, uma chamada por célula de 0,1° |

- **Bairro = distrito do IBGE.** São os 96 distritos da cidade de São Paulo. Os nomes coincidem com os do cadastro de refúgios da API .NET (Penha, Vila Matilde, Itaquera, Tatuapé).
- **% de 60+:** de 11,17% a 30,01% entre os distritos. A média da cidade, ponderada pela população, é 17,66%.
- **Clima de um dia:** é o da **pior hora** (a de maior índice de calor). O serviço em produção usa a mesma regra na previsão de hoje (`clima.pior_hora`).
- **Tamanho:** 105.216 linhas (96 distritos × 1.096 dias).
- **Resolução:** os 96 distritos caem em 17 células do ERA5-Land, então distritos vizinhos compartilham o mesmo clima. O que muda entre eles no mesmo dia é a proporção de idosos.

Distribuição das classes:

| Ano | baixo | médio | alto |
|---|---|---|---|
| 2023 | 59,5% | 34,4% | 6,2% |
| 2024 | 56,4% | 38,4% | 5,2% |
| 2025 (teste) | 66,3% | 30,8% | 2,9% |

A classe **alto é rara** (1.018 linhas no teste). Por isso a métrica principal é a **macro-F1**, que dá o mesmo peso às três classes, e os modelos usam `class_weight="balanced"`.

## 3. O rótulo é derivado, não observado

Não existe dado público de "risco de calor por bairro". O rótulo é calculado por regra (`training/rotulo.py`):

```
índice ajustado = índice de calor da NOAA na pior hora
                  + 0,2 °C × (% de 60+ do bairro − 17,66)

alto   se índice ajustado ≥ 32,2 °C   (90 °F, início de "Extreme caution" da NOAA)
médio  se índice ajustado ≥ 26,7 °C   (80 °F, início de "Caution")
baixo  abaixo disso
```

Consequências:

- O modelo aprende **esta regra**, e não o risco real. Uma macro-F1 alta mostra que ele reproduz a regra a partir de temperatura, umidade e % de idosos. Não prova que ele acerta quem vai passar mal.
- Os pesos são escolhas do grupo e estão justificados em `app/config.py`: as faixas são as da NOAA, e o peso de 0,2 °C por ponto percentual faz um bairro 10 p.p. mais idoso que a cidade subir 2 °C.
- O índice de calor **não entra** como feature. Se entrasse, bastaria um limiar sobre ele. O modelo precisa aprender a relação não linear entre temperatura e umidade, e é aí que os algoritmos se diferenciam.

## 4. Metodologia

- **Divisão por tempo:** treino em 2023–2024 (70.176 linhas) e teste em 2025 (35.040 linhas). Uma divisão ao acaso poria o mesmo dia de distritos vizinhos, com clima idêntico, nos dois lados, e a métrica ficaria inflada.
- **Hiperparâmetros da Random Forest:** escolhidos com `GridSearchCV` e validação cruzada **por ano** (treina em 2023 e valida em 2024, e o inverso). Grade: `max_depth` ∈ {6, 10, None} e `min_samples_leaf` ∈ {5, 20, 50}, com 200 árvores. Melhor configuração: `max_depth=None` e `min_samples_leaf=5`, com macro-F1 de validação de 0,931.
- **Baseline:** regra só pela temperatura do ar, com os dois limites escolhidos no treino pela melhor macro-F1 (26,0 °C e 31,0 °C). Os limites foram calibrados de propósito, para o ML ser comparado com uma regra justa e não com números chutados.
- **Regressão logística:** padronização das entradas e `class_weight="balanced"`.

## 5. Resultados no teste (2025)

| Modelo | Macro-F1 | Precisão alto | Recall alto | F1 alto | F1 médio |
|---|---|---|---|---|---|
| Baseline (temperatura do ar) | 0,778 | 0,567 | 0,451 | 0,503 | 0,874 |
| Regressão logística | 0,957 | 0,845 | **0,999** | 0,916 | 0,966 |
| **Random Forest (servido)** | **0,973** | **0,897** | 0,981 | **0,937** | **0,986** |

Matrizes de confusão (linhas = classe real, colunas = classe prevista):

**Baseline**

| real \ previsto | baixo | médio | alto |
|---|---|---|---|
| baixo | 21.980 | 1.235 | 0 |
| médio | 687 | 9.770 | 350 |
| alto | 0 | 559 | 459 |

**Regressão logística**

| real \ previsto | baixo | médio | alto |
|---|---|---|---|
| baixo | 22.833 | 382 | 0 |
| médio | 165 | 10.456 | 186 |
| alto | 0 | 1 | 1.017 |

**Random Forest**

| real \ previsto | baixo | médio | alto |
|---|---|---|---|
| baixo | 23.101 | 114 | 0 |
| médio | 54 | 10.638 | 115 |
| alto | 0 | 19 | 999 |

Importância das features na RF: temperatura 0,79, umidade 0,13, % de 60+ 0,08.

## 6. Análise

- **O baseline erra justo onde importa.** Ele só olha a temperatura e acerta 45% dos dias de risco alto. Os dias que ele perde são quentes e úmidos (o índice de calor sobe com a umidade) ou caem em bairros mais idosos. Os dois casos dependem de informação que o termômetro sozinho não tem.
- **A regressão logística chegou perto da RF** (0,957). Na faixa de clima de São Paulo, a fronteira entre as classes é quase linear em temperatura e umidade. O que falta para ela é a curvatura do índice de calor: ela erra mais na fronteira médio/alto (186 dias médios previstos como alto, precisão de 0,845 em alto).
- **A RF tem a melhor macro-F1** e a melhor precisão em alto, por isso é o modelo servido (decisão do grupo).
- **Trade-off que fica registrado:** a RF classifica como médio 19 dos 1.018 dias de risco alto (recall de 0,981). A regressão logística erra só 1 (recall de 0,999), mas dispara alto em mais dias que não são. Para idosos, perder um dia alto custa mais que um alarme a mais. Um próximo passo seria baixar o limiar de decisão da classe alto na RF, ou servir a logística quando o objetivo for só não perder dia alto. Na prática, um dia previsto como médio também recebe "beba água, evite o sol entre 10h e 16h e ligue 192 se passar mal", então o erro não deixa a pessoa sem orientação.
- **Nenhum modelo confunde baixo com alto** (zero nas duas pontas da matriz). Os erros ficam sempre entre classes vizinhas.
- **A queda da validação (0,931) para o teste (0,973)** vem de 2025 ter tido menos dias na fronteira médio/alto (2,9% de alto contra 5 a 6% nos anos anteriores). O teste foi um ano "mais fácil", não houve vazamento de dados.

## 7. Avaliação da IA generativa

### Como o texto é controlado

1. O prompt (`app/prompts/alerta.txt`) traz regras, um exemplo por nível de risco e o Guia do calor (`app/content/guia_calor.txt`).
2. O LLM recebe só bairro, risco, números do clima e nomes de refúgios com vaga (no máximo 2). Nenhum dado pessoal do idoso.
3. A resposta passa por `motivo_invalido()`. O texto é recusado e trocado pelo texto padrão se:
   - estiver vazio ou tiver mais de 400 caracteres;
   - for risco alto sem o SAMU 192;
   - for risco alto, houver refúgio com vaga, e o texto não citar nenhum;
   - tiver número de 3 dígitos ou mais diferente de 192 (telefone ou endereço inventado);
   - citar biblioteca, UBS, CEU, escola etc. fora dos refúgios devolvidos pela API;
   - afirmar algo que a API não informa (ar-condicionado);
   - copiar o nome dos exemplos do prompt.
4. Os textos padrão passam pela mesma validação. Há um teste para cada nível, com e sem refúgio.

### Testes com o modelo real

Seis casos (Penha alto com 2 refúgios, Penha médio, Penha baixo, Itaquera alto sem API, Vila Matilde médio, Tatuapé alto sem refúgio), rodados duas vezes no Ollama local:

| Versão do prompt | Aprovados pela validação | Problemas observados |
|---|---|---|
| 1ª (só regras) | 4 de 4 | Inventou "que têm ar-condicionado"; disse "vai fazer calor" num dia baixo de 22 °C; chamou a pessoa de "idoso"; erros de concordância |
| 2ª (com exemplos) | 10 de 10 | Tom correto, mas os textos eram cópias dos exemplos, sem bairro nem temperatura |
| 3ª (exemplos com bairro e graus) | 12 de 12 | Texto com bairro e temperatura; "26 graus" para 26,7 °C (corrigido mandando o valor já arredondado) |

O caso da 1ª versão mostra por que a validação existe: o texto com "ar-condicionado" **passou** nas regras daquela época, e a regra de afirmações proibidas foi criada a partir dele.

**Latência:** a primeira chamada levou 28,6 s, para carregar o modelo do disco. Com o modelo na memória, cada alerta leva de 4 a 6 s, com até 11 s na primeira chamada de uma rajada. Por isso o serviço carrega o modelo em segundo plano na subida (`OllamaLLM.aquecer`) e o mantém na memória por 30 min (`keep_alive`).

**Problemas que continuam:**
- Às vezes erra o artigo do bairro ("na Itaquera" em vez de "em Itaquera").
- Em risco baixo, às vezes acrescenta "Se passar mal, ligue 192". Não é alarmante, mas não estava pedido.
- Com dois refúgios, escreveu "estão abertas" no feminino para "Biblioteca ... ou CEU ...".

Nenhum desses problemas muda o sentido do alerta, então a validação não os recusa.

## 8. Casos de teste

`pytest -v` roda **130 testes**, sem rede: Open-Meteo, API .NET e Ollama são simulados com `respx` ou com objetos falsos.

| Arquivo | Testes | O que cobre |
|---|---|---|
| `test_config.py` | 6 | Leitura do `.env`, padrões, timeout inválido |
| `test_schemas.py` | 8 | Clima simulado completo, faixas, campos extras recusados |
| `test_refugio_client.py` | 12 | Login, reuso do token, 401 com novo login, 429 curto e longo, timeout, API fora do ar |
| `test_indice_calor.py` | 9 | Fórmula da NOAA contra a tabela da NWS |
| `test_clima.py` | 6 | Pior hora do dia, horas sem dado, falhas do Open-Meteo |
| `test_dados.py` | 12 | Rótulo, leitura do IBGE (CSV e GeoPackage), resumo diário |
| `test_treino.py` | 4 | Baseline, divisão por tempo, matriz de confusão |
| `test_risco.py` | 11 | Catálogo sem acento, carga do modelo, modelo real nos cenários do README |
| `test_llm.py` | 36 | Prompt, cada regra de validação, cliente do Ollama, textos padrão |
| `test_endpoints.py` | 11 | Fluxo do Postman, 404, 422, nenhum dado pessoal no prompt |
| `test_cenarios_falha.py` | 15 | API .NET fora do ar (4 tipos de falha), LLM fora do ar, texto inválido, Open-Meteo fora do ar, sem modelo |

### Teste manual com o serviço real (16/11/2026)

Uvicorn com o modelo treinado, Open-Meteo de verdade e Ollama local. A API .NET não estava acessível nesse dia.

| Passo do README | Resultado |
|---|---|
| 1. `GET /health` | `200`, `modelo_carregado: true` |
| 4. `GET /bairros` | `200`, 96 bairros |
| 5. Penha, clima real | `200`, 26,7 °C e 55% → médio (0,99), texto do LLM |
| 6. Penha, 40 °C e 30% | `200`, alto (0,99), "Se passar mal, ligue 192.", texto do LLM |
| 7. Penha, 22 °C e 60% | `200`, baixo (0,999), "o dia está tranquilo" |
| 8. Bairro inexistente | `404` com a dica de `GET /bairros` |
| 8. `temperatura_c: "muito quente"` | `422` apontando `body.temperatura_c` |
| 8. API .NET fora do ar | `200`, `refugios_consultados: false`, alerta sem refúgio |
| 8. LLM indisponível (`LLM_MODEL` inexistente) | `200`, `origem_texto: "fallback"`, texto padrão do risco alto |

Os passos 2 e 3 (login e listagem na API .NET) e o alerta citando refúgios reais foram feitos depois, com a API publicada no Render.

### Integração com a API .NET no Render (19/11/2026)

Serviço com o modelo treinado, apontando para `https://refugio-net.onrender.com` com a conta de teste `maria@email.com` (IDOSO). O Ollama estava desligado, então os textos saíram do fallback. Clima simulado: 40 °C e 30% de umidade.

| Bairro | Resultado |
|---|---|
| Login (`POST /auth/login`) | `200`, token recebido |
| Penha | `200`, alto, `refugios_consultados: true`; CEU Penha, Biblioteca Municipal da Penha e dois refúgios de teste ("Sala Unica") criados na validação da API; o alerta cita o CEU Penha |
| Itaquera | `200`, alto, Centro Comunitário Itaquera no alerta |
| Tatuapé | `200`, alto, nenhum refúgio (o único cadastrado lá está inativo); alerta genérico com o 192 |

A listagem filtra por `ativo=true` e o serviço descarta refúgios sem vaga, como nos testes com respostas no formato do `RefugioResponse` do .NET.

## 9. Limitações e uso responsável

- **Rótulo derivado** (seção 3): a métrica mede consistência com a regra, não acerto clínico.
- **Resolução do clima:** a grade de ~11 km do ERA5-Land não vê ilha de calor urbana, e distritos vizinhos recebem o mesmo clima.
- **Treino e produção usam modelos de clima diferentes:** o treino usa a reanálise ERA5-Land e a produção usa a previsão do Open-Meteo (`best_match`). A regra da pior hora é a mesma, mas pode haver diferença sistemática de alguns décimos de grau.
- **Fora do modelo:** condições de moradia, saúde individual e morar sozinho.
- **Privacidade:** nenhum dado pessoal vai ao LLM, o pedido recusa campos extras (`extra=forbid`) e o LLM roda localmente, sem enviar dados a terceiros.
- **Orientação médica:** o alerta não substitui orientação médica. Em risco alto, o texto sempre manda ligar para o SAMU (192), e isso é garantido pela validação.
- **Sem autenticação** na versão de demonstração.
