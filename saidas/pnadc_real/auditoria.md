# Auditoria do painel

Gerado em 2026-09-22 23:48 UTC a partir de `../data/processed/pnadc_transicoes.parquet` (formato `pares`).

## Alertas

- ⚠️ Quebra na série de mudança de grande grupo (mediana 20.3%) nas origens 2020T1, 2020T2, 2020T3, 2020T4, 2021T1, 2021T2, 2021T3. Janela atípica configurada: 2020T1 a 2021T3.
- ⚠️ 19 COD sem AIOE (1.08% do peso). Ficam fora dos quartis.

## Decisões embutidas

- **2022T4 fica fora.** O ChatGPT saiu em 30/11/2022, então o trimestre é parcialmente tratado. Sai todo par com origem ou destino nesse trimestre.
- **Pré** = pares com destino até 2022T3. **Pós** = pares com origem a partir de 2023T1.
- **Quartis de exposição fixados no pré** (AIOE da ocupação de origem, ponderado pelos ocupados). Cortes: -0.990, -0.385, 0.711.
- **Só pares de trimestres consecutivos.** Um salto de dois trimestres não conta como transição.
- **Mobilidade no grande grupo COD (1 dígito)**, para não inflar a mobilidade com erro de codificação entre entrevistas.
- **Janela de coleta atípica** (origens 2020T1 a 2021T3): excluída do pré; a tabela A com ela fica em `A_sensibilidade_com_janela_atipica.csv`.

## Integridade do painel

- Células: 4,014,438; origens ocupadas: 4,017,289; pares encontrados: 3,222,007.
- Registros com chave duplicada no trimestre (não pareados): 0.
- No formato de pares, sexo, nascimento, visita seguinte e trimestre seguinte já foram exigidos no pareamento (BigQuery). Chave duplicada não pareia. Aqui entram a taxa de pareamento e as duplicatas registradas.

### Taxa de pareamento por trimestre de origem

| Trimestre | Pareados (peso) |
| --- | --- |
| 2019T1 | 81.0% |
| 2019T2 | 81.1% |
| 2019T3 | 82.7% |
| 2019T4 | 79.7% |
| 2020T1 | 76.5% |
| 2020T2 | 83.1% |
| 2020T3 | 81.0% |
| 2020T4 | 79.3% |
| 2021T1 | 78.7% |
| 2021T2 | 78.0% |
| 2021T3 | 73.6% |
| 2021T4 | 73.6% |
| 2022T1 | 74.9% |
| 2022T2 | 76.9% |
| 2022T3 | 76.3% |
| 2022T4 | 77.6% |
| 2023T1 | 78.3% |
| 2023T2 | 80.0% |
| 2023T3 | 79.3% |
| 2023T4 | 82.0% |
| 2024T1 | 82.2% |
| 2024T2 | 83.1% |
| 2024T3 | 81.4% |
| 2024T4 | 82.5% |
| 2025T1 | 82.7% |
| 2025T2 | 83.1% |
| 2025T3 | 82.1% |

## Ocupados sem AIOE

1.08% do peso dos ocupados na origem (33,758 observações) está sem AIOE.

COD fora do crosswalk:

| COD | Obs. | % do peso |
| --- | --- | --- |
| 0412 | 12247 | 0.397 |
| 0210 | 9351 | 0.303 |
| 0512 | 2335 | 0.076 |
| 0110 | 2236 | 0.074 |
| 9510 | 1542 | 0.052 |
| 1111 | 1972 | 0.047 |
| 0411 | 1450 | 0.045 |
| 0511 | 518 | 0.019 |
| 9332 | 646 | 0.016 |
| 0000 | 398 | 0.014 |
| 5161 | 225 | 0.009 |
| 8159 | 155 | 0.007 |
| 3413 | 192 | 0.006 |
| 9613 | 130 | 0.004 |
| 5168 | 118 | 0.004 |
| 8155 | 88 | 0.004 |
| 7133 | 67 | 0.003 |
| 2659 | 81 | 0.002 |
| 4213 | 7 | 0.0 |

## Quebra da coleta telefônica

Mudança de grande grupo entre todos os ocupados, por trimestre de origem. Mediana: 20.3%. Trimestres a mais de 30% da mediana: 2020T1, 2020T2, 2020T3, 2020T4, 2021T1, 2021T2, 2021T3.

## Composição pré/pós

Pares por período: pré 917,015; pós 1,436,618; janela atípica 620,787; excluídos por 2022T4 247,587.

| Dimensão | Categoria | Pré (%) | Pós (%) | Dif. (p.p.) |
| --- | --- | --- | --- | --- |
| quartil | Q1 | 30.2 | 28.4 | -1.8 |
| quartil | Q2 | 19.9 | 20.7 | 0.9 |
| quartil | Q3 | 25.0 | 25.7 | 0.7 |
| quartil | Q4 | 24.9 | 25.2 | 0.3 |
| grupo_origem | 0 Forças armadas, policiais e bombeiros militares | 1.0 | 0.9 | -0.1 |
| grupo_origem | 1 Diretores e gerentes | 4.2 | 3.6 | -0.6 |
| grupo_origem | 2 Profissionais das ciências e intelectuais | 12.0 | 13.5 | 1.4 |
| grupo_origem | 3 Técnicos e profissionais de nível médio | 8.3 | 9.1 | 0.8 |
| grupo_origem | 4 Apoio administrativo | 8.3 | 8.4 | 0.1 |
| grupo_origem | 5 Serviços, vendedores do comércio e mercados | 22.3 | 21.9 | -0.5 |
| grupo_origem | 6 Qualificados da agropecuária, florestais, caça e pesca | 5.8 | 5.0 | -0.8 |
| grupo_origem | 7 Operários, artesãos da construção e ofícios mecânicos | 13.3 | 12.9 | -0.4 |
| grupo_origem | 8 Operadores de instalações e máquinas e montadores | 8.6 | 9.3 | 0.7 |
| grupo_origem | 9 Ocupações elementares | 16.2 | 15.5 | -0.7 |
