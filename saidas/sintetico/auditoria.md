# Auditoria do painel

Gerado em 2026-09-23 00:02 UTC a partir de `saidas/sintetico/painel_sintetico.parquet` (formato `individuos`).

## Alertas

- ⚠️ 300 linhas duplicadas em id x trimestre (150 ids). Elas saem do pareamento.
- ⚠️ 3.02% dos ids pulam ao menos um trimestre. Esses saltos não contam como transição.
- ⚠️ 3 COD sem AIOE (0.99% do peso). Ficam fora dos quartis.

## Decisões embutidas

- **2022T4 fica fora.** O ChatGPT saiu em 30/11/2022, então o trimestre é parcialmente tratado. Sai todo par com origem ou destino nesse trimestre.
- **Pré** = pares com destino até 2022T3. **Pós** = pares com origem a partir de 2023T1.
- **Quartis de exposição fixados no pré** (AIOE da ocupação de origem, ponderado pelos ocupados). Cortes: -0.904, -0.257, 0.940.
- **Só pares de trimestres consecutivos.** Um salto de dois trimestres não conta como transição.
- **Mobilidade no grande grupo COD (1 dígito)**, para não inflar a mobilidade com erro de codificação entre entrevistas.
- **Janela de coleta atípica** (origens 2020T1 a 2021T3): excluída do pré; a tabela A com ela fica em `A_sensibilidade_com_janela_atipica.csv`.

## Integridade do painel

- Linhas: 173,628; ids: 45,430.
- Duplicatas id × trimestre: 300 linhas em 150 ids.
- Sexo inconsistente no mesmo id: 193 ids (0.42%).
- Idade inconsistente no mesmo id (recua ou avança mais de 2 anos): 197 ids (0.43%).
- Saltos entre entrevistas: 1,381 transições em 1,373 ids (3.02%).
- Origens ocupadas: 107,719; com entrevista seguinte consecutiva: 77,920; descartadas por salto: 862.

### Retenção da 1ª à 5ª visita

Coorte: ids observados pela primeira vez na 1ª visita.

| Visita | Ids | % da coorte |
| --- | --- | --- |
| 1 | 39867 | 100.0 |
| 2 | 35203 | 88.3 |
| 3 | 31418 | 78.81 |
| 4 | 28051 | 70.36 |
| 5 | 25066 | 62.87 |

## Ocupados sem AIOE

0.99% do peso dos ocupados na origem (775 observações) está sem AIOE.

COD fora do crosswalk:

| COD | Obs. | % do peso |
| --- | --- | --- |
| 5168 | 440 | 0.588 |
| 0110 | 235 | 0.278 |
| 9999 | 100 | 0.129 |

## Quebra da coleta telefônica

Mudança de grande grupo entre todos os ocupados, por trimestre de origem. Mediana: 5.9%. Trimestres a mais de 30% da mediana: nenhum.

## Composição pré/pós

Pares por período: pré 21,037; pós 29,906; janela atípica 21,040; excluídos por 2022T4 5,937.

| Dimensão | Categoria | Pré (%) | Pós (%) | Dif. (p.p.) |
| --- | --- | --- | --- | --- |
| quartil | Q1 | 25.5 | 25.2 | -0.3 |
| quartil | Q2 | 26.0 | 27.6 | 1.7 |
| quartil | Q3 | 23.7 | 22.8 | -0.9 |
| quartil | Q4 | 24.8 | 24.3 | -0.5 |
| grupo_origem | 0 Forças armadas, policiais e bombeiros militares | 0.3 | 0.3 | -0.1 |
| grupo_origem | 1 Diretores e gerentes | 6.8 | 6.4 | -0.4 |
| grupo_origem | 2 Profissionais das ciências e intelectuais | 11.6 | 10.9 | -0.7 |
| grupo_origem | 3 Técnicos e profissionais de nível médio | 11.3 | 11.3 | -0.0 |
| grupo_origem | 4 Apoio administrativo | 11.2 | 11.7 | 0.5 |
| grupo_origem | 5 Serviços, vendedores do comércio e mercados | 11.6 | 12.3 | 0.7 |
| grupo_origem | 6 Qualificados da agropecuária, florestais, caça e pesca | 11.6 | 11.9 | 0.3 |
| grupo_origem | 7 Operários, artesãos da construção e ofícios mecânicos | 11.6 | 11.4 | -0.2 |
| grupo_origem | 8 Operadores de instalações e máquinas e montadores | 11.5 | 11.7 | 0.1 |
| grupo_origem | 9 Ocupações elementares | 12.4 | 12.2 | -0.2 |
