# Painel analítico e data storytelling — pré-Diff-in-Diff

Este documento acompanha `painel_dissertacao.html` e `base_dissertacao.py`. Ele responde às
oito partes pedidas: como a base foi revisada, o que as estatísticas descritivas mostram, o
que as ocupações mais expostas parecem, e o que ainda falta para tratar qualquer coisa aqui
como causal.

**Tudo que aparece no HTML vem de `saidas/dissertacao/dashboard_data_v2.json`, calculado
por `base_dissertacao.py` diretamente sobre `IDP/data/processed/pnadc_transicoes.parquet`.
Nenhum número foi digitado à mão. Nenhum arquivo do IDP foi alterado — o script só lê.**

## Como rodar

```bash
pip install -r requirements.txt
python base_dissertacao.py          # lê ../IDP, escreve em saidas/dissertacao/
```

## 1. Revisão da base — quadro-resumo

| | |
| --- | --- |
| **Unidade de observação** | Célula agregada por trimestre × UF × UPA × ocupação de origem × ocupação de destino × covariáveis — não uma linha por pessoa. A auto-junção pessoa a pessoa acontece no BigQuery e só descem células já agregadas (o IDP proíbe baixar microdado individual). Como as regressoras e desfechos são constantes dentro da célula, a estimação em células reproduz a estimação pessoa a pessoa — mas por isso "quantidade de pessoas" abaixo é peso amostral e contagem de pares (`n`), não um ID único, que este script não tem. |
| **Fontes** | PNAD Contínua trimestral (IBGE, via basedosdados); AIOE (Felten, Raj e Seamans); crosswalk COD→ISCO-08→SOC2010 (reprodução arquivada do BLS); nomes de ocupação do `Estrutura_Ocupacao_COD.xls` do IBGE. |
| **Consolidação** | Pareamento pessoa a pessoa no BigQuery (mesmo domicílio, número de ordem, visita seguinte, sexo/dia/mês de nascimento iguais, ano de nascimento com diferença ≤1, idade avançando 0–1 ano); exposição do COD é a média dos SOC ponderada pelo crosswalk, ignorando elos sem valor. |
| **Período** | 2019T1 a 2025T3 — 27 trimestres de origem. |
| **Escala** | 4.014.438 células; 4.017.289 pares amostrais (n); ~2,0 bilhões de peso amostral acumulado de ocupados na origem; 436 CODs de origem distintos, 434 de destino. |
| **Ausentes** | 1,08% do peso dos ocupados sem AIOE (militares e um grupo sem correspondência no BLS, por desenho); 0 chaves duplicadas e 0 pesos inválidos no arquivo consolidado. |
| **Inconsistência corrigida nesta etapa** | O parquet do IDP grava alguns CODs sem zero à esquerda (`"412"` em vez de `"0412"`, todos do grande grupo 0 — forças armadas/policiais/bombeiros; ~550 células em 4 milhões). Sem correção, essas células perdiam o grande grupo. `base_dissertacao.py` reaplica o mesmo `cod4()` (zero-preenchimento) que `painel_storytelling.py` já usava — documentado no código, não uma alteração no arquivo do IDP. |
| **Filtros aplicados** | Idade 18–65 (já aplicado na consulta do IDP); origem é pessoa ocupada; só pares de trimestres consecutivos (a auto-junção liga t a t+1 diretamente); 2022T4 fora do pré/pós (ChatGPT lançado em 30/11/2022, trimestre parcialmente tratado); coleta telefônica da pandemia (origens 2020T1–2021T3) fora do pré; quartis de AIOE fixados na distribuição do pré-choque, ponderada pelo peso; mobilidade medida no grande grupo COD (1 dígito), não no código de 4 dígitos. |
| **Alterações na base original** | Nenhuma. Toda reclassificação (período, quartil, destino) é feita em memória por `base_dissertacao.py`. |

Quadro completo, com a lista de trimestres abaixo de 70% de pareamento e o detalhamento dos
CODs sem AIOE: `saidas/dissertacao/quadro_resumo.json`.

## 2. Estatísticas descritivas

De quem estava ocupado na origem, entre os pareados (a entrevista seguinte foi encontrada):

| | Pré-choque | Pós-choque |
| --- | --- | --- |
| Taxa de pareamento | 78,5% | 81,5% |
| Permaneceram na mesma ocupação (grande grupo) | 70,3% | 70,6% |
| Mudaram de ocupação (grande grupo) | 20,7% | 21,4% |
| Saíram do emprego | 9,1% | 8,0% |
| — dos quais, ficaram desempregados | 3,4% | 2,2% |
| — dos quais, saíram da força de trabalho | 5,7% | 5,8% |
| Migraram para informalidade (entre os formais na origem) | 7,9% | 8,8% |

**Entradas na força de trabalho não são observáveis com esta base.** O painel de transições do
IDP só existe a partir de quem estava *ocupado* na entrevista de origem — uma pessoa que sai do
desemprego ou da inatividade para um emprego não gera uma célula de origem aqui. Isso está
documentado explicitamente no JSON (`descritivas.entradas_na_forca_de_trabalho`) para não virar
um resultado nulo silencioso.

**Maiores ocupações de origem e de destino:** `saidas/dissertacao/top_ocupacoes_origem.csv` e
`top_ocupacoes_destino.csv` (COD, nome, peso, % do total).

**Matriz de transição** (origem → destino, quantidade e percentual, por quartil de exposição e
por período): `saidas/dissertacao/matriz_transicao.csv`. Pergunta-chave — *para onde vão os que
saem das ocupações mais expostas?* — no Ato IV do dashboard: majoritariamente para **outro
grande grupo ocupacional**, não para o desemprego, em todos os quartis.

## 3. Empregos potencialmente mais afetados pela IA

`saidas/dissertacao/ocupacoes_exposicao.csv` — uma linha por COD (4 dígitos) × período
(pré/pós), com AIOE, peso de ocupados, e a composição de saída (% que fica no mesmo grande
grupo, % que muda de grande grupo, % desempregado, % fora da força, % que se informaliza entre
os formais). Só entram ocupações com pelo menos 80 pares no pré, para não expor ranking de
células pequenas.

**Mais expostas (pré-choque):** dirigentes financeiros, profissionais do direito, contadores,
analistas financeiros, psicólogos, economistas — funções financeiras, jurídicas e de gestão.

**Menos expostas:** lavadeiros de roupa, atletas, telhadores, trabalhadores elementares da
construção e da jardinagem, pintores — ocupações manuais.

**Isto é descritivo, não um veredito.** Nenhuma ocupação é classificada aqui como tendo perdido
emprego "por causa da IA". O que o arquivo mostra é o tamanho e a composição de saída de cada
ocupação, associados ao grau de exposição — a leitura causal fica para a Seção 7/6 do dashboard.

## 4–6. Dashboard

`painel_dissertacao.html` — seis atos: (1) o mercado antes/depois do ChatGPT com os KPIs e a
série de emprego por quartil; (2) o ranking de exposição e a distribuição do AIOE; (3) o quadro
"O que aconteceu com os trabalhadores?" e a comparação pré/pós por quartil; (4) a matriz de
transição (heatmap) e o Sankey de fluxos entre grandes grupos; (5) a síntese dos achados
descritivos; (6) a documentação das variáveis para o Diff-in-Diff.

Identidade visual: verde escuro (`#0b4d30`) como cor principal, verde intermediário (`#237a4c`),
verde claro (`#7cc296`) para destaque, branco como fundo e cinza claro para elementos
auxiliares — a mesma rampa de verde também codifica os quartis de exposição (Q1 claro → Q4
escuro), então o gráfico de exposição e a identidade visual usam a mesma linguagem de cor.
Categorias de desfecho (permaneceu/mudou/desemprego/fora/informalidade) usam uma paleta
categórica separada e validada (`dataviz` skill) para não colidir com a escala de exposição.

**Títulos com conclusão, só quando sustentados pelos dados** — dois exemplos que passaram por
essa checagem antes de entrar no HTML:

- *"Desde 2022, o emprego cresce mais nos quartis mais expostos à IA... do que no menos
  exposto"* — usado porque o crescimento do emprego médio trimestral, entre 2022 e 2025, é
  monótono nos quatro quartis (Q1: −0,3%; Q2: +2,3%; Q3: +6,0%; Q4: +8,4%). Calculado por médias
  trimestrais dentro do ano, para não distorcer com o fato de 2025 só ter três trimestres.
- **Rejeitado:** um título do tipo "trabalhadores mais expostos mudam mais de ocupação depois do
  ChatGPT" não entrou no dashboard. A diferença pré/pós em "mudou de ocupação" é parecida em
  todos os quartis (+0,6 a +0,8 p.p.) — o gradiente Q4 > Q1 é grande, mas já existia antes do
  choque. O título usado (Seção 3) é o oposto: *"a diferença entre quartis é maior no nível do
  que na variação pré/pós"*.

## 7. Preparação para o Diff-in-Diff

Documentado em `saidas/dissertacao/did_variaveis.json` e na Seção 6 do dashboard — reproduz a
especificação já fixada em `IDP/METODOLOGIA.md §5`, não propõe nada novo:

| Papel | Variável |
| --- | --- |
| Unidade de observação | Par pessoa-trimestre, agregado em células por UF × UPA × ocupação de origem × covariáveis |
| Tratamento / exposição | `aioe_origem` (contínuo, padronizado; desvio-padrão 0,9445 entre 416 códigos); interação `aioe_origem:pos` |
| Período pré/pós | Pré = destino até 2022T3; pós = origem a partir de 2023T1; excluídos 2022T4 e 2020T1–2021T3 |
| Outcomes planejados | `pareado`, `muda_ocupacao_2`, `muda_ocupacao_3`, `sai_do_emprego`, `formal_para_informal`, `mobilidade_descendente_aioe`, `mobilidade_ascendente_aioe` |
| Controles | `telework:pos`, idade, idade², sexo, raça, escolaridade, tempo de emprego, tamanho da empresa, setor |
| Efeitos fixos | `cod_origem`; `sigla_uf × mês` |
| Pesos / cluster | Peso V1028 da entrevista de origem; cluster por UPA |

**Por que não é o TWFE clássico:** o viés de adoção escalonada não se aplica — todo mundo é
"tratado" na mesma data-calendário. O risco aqui é o tratamento contínuo (intensidade do AIOE),
que exige uma versão mais forte de tendências paralelas — Callaway, Goodman-Bacon & Sant'Anna
(2024) (`IDP/artigos/callaway2024.pdf`) e Rambachan & Roth (2023) para violações limitadas de
tendência prévia (`IDP/artigos/rambachan2023.pdf`).

**Antes de estimar:** estudo de evento em torno de 2022T4; teste formal de tendências prévias
nos quatro quartis (a série da Seção 1 é o primeiro teste visual); robustez sem a janela de
coleta telefônica; especificação com tratamento contínuo (não só o corte por quartil usado aqui
para visualização).

## 8. Entregáveis

| Arquivo | Conteúdo |
| --- | --- |
| `painel_dissertacao.html` | dashboard completo (tópico 4) |
| `base_dissertacao.py` | código que gera todos os números (tópico 4, item 2) |
| `saidas/dissertacao/*.csv` | tabelas consolidadas (tópico 4, item 3) |
| `saidas/dissertacao/quadro_resumo.json` | construção do painel (tópico 4, item 4) |
| `saidas/dissertacao/descritivas_geral.json`, `o_que_aconteceu.json` | estatísticas descritivas (item 5) |
| `saidas/dissertacao/matriz_transicao.csv` | fluxos ocupacionais (item 6) |
| `saidas/dissertacao/ocupacoes_exposicao.csv` | ocupações por exposição (item 7) |
| Este arquivo + comentários em `base_dissertacao.py` | documentação das decisões (item 8) |
