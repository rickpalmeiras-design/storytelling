# Storytelling: exposição à IA e mobilidade ocupacional na PNADC

Material da reunião. Um script cobre os tópicos 1 e 2 e gera o `dashboard_data.json`
que alimenta o HTML do tópico 3.

```bash
pip install -r requirements.txt

# Teste com dados sintéticos (painel pessoa x trimestre)
python gera_sintetico.py
python painel_storytelling.py

# Painel real do IDP (pares já construídos no BigQuery), com o repositório
# rickpalmeiras-design/idp clonado ao lado deste
python painel_storytelling.py --formato pares \
    --painel ../IDP/data/processed/pnadc_transicoes.parquet \
    --exposicao ../IDP/data/interim/exposicao_cod.parquet \
    --saida saidas/pnadc_real
```

Em outro painel, basta ajustar os nomes de colunas no bloco `CONFIG` de `painel_storytelling.py`.

## Formatos de entrada

| `formato` | Uma linha é | Tópico 1 |
| --- | --- | --- |
| `individuos` | pessoa x trimestre (id, ano, trimestre, visita, sexo, idade, condição, COD, peso) | todas as checagens |
| `pares` | célula origem → destino já pareada, como `pnadc_transicoes.parquet` do IDP | taxa de pareamento e duplicatas; sexo, nascimento e visita seguinte já foram exigidos no pareamento |

## Tópico 1: auditoria (`auditoria.md`)

Alertas automáticos para:

- duplicatas id × trimestre;
- sexo e idade inconsistentes dentro do mesmo id (sinal de pareamento errado);
- saltos entre entrevistas e retenção da 1ª até a 5ª visita;
- ocupados sem AIOE, listando os COD que ficaram fora do crosswalk;
- composição pré/pós;
- quebra na série de mudança de grande grupo (coleta telefônica).

Decisões embutidas:

- **2022T4 fica fora.** O ChatGPT saiu em 30/11, então o trimestre é parcialmente tratado.
  Sai todo par com origem ou destino em 2022T4. Pré = destino até 2022T3; pós = origem a partir de 2023T1.
- **Quartis de exposição fixados na distribuição do pré**, ponderada pelos ocupados. O pós não contamina os cortes.
- **Só pares de trimestres consecutivos.** Um salto de dois trimestres não conta como transição.
- **Grande grupo COD (1 dígito).** No nível de 4 dígitos, o erro de codificação entre entrevistas infla a mobilidade.
- **Janela de coleta atípica fora do pré** (origens 2020T1 a 2021T3, `CONFIG["janela_atipica"]`).
  A tabela A com a janela incluída sai como sensibilidade.

## Tópico 2: para onde as pessoas vão

Sempre a partir de quem estava ocupado na origem.

| Saída | Conteúdo |
| --- | --- |
| `A_destino_por_quartil.csv` | destino no trimestre seguinte (mesmo grupo, outro grupo, desocupado, fora da força) por quartil, pré vs pós, diferença em p.p. |
| `A_sensibilidade_com_janela_atipica.csv` | a mesma tabela com 2020T1–2021T3 de volta no pré |
| `B_grupo_destino_dos_que_mudam.csv` | grande grupo de destino de quem muda de grupo |
| `D_direcao_exposicao.csv` | quem muda vai para quartil mais, igual ou menos exposto; ΔAIOE médio |
| `E_serie_Q4_vs_Q1.csv` | série trimestral de Q4 vs Q1: mudança de grupo e saída do emprego |
| `sankey_fluxos.csv`, `sankey.html` | fluxos entre grandes grupos, pré e pós |
| `dashboard_data.json` | tudo acima mais a auditoria e o mapa dos quartis, para o HTML |

## Primeira leitura do painel real (`saidas/pnadc_real/`)

Painel do IDP, origens de 2019T1 a 2025T3, com 917 mil pares no pré e 1,44 milhão no pós.

1. **A coleta telefônica quebra a série.** A mudança de grande grupo, que costuma ficar em torno de 20%,
   cai para 8–13% nas origens de 2020T1 a 2021T3, em todos os quartis. Com a janela no pré, a tabela A
   mostra +5,2 a +7,0 p.p. de mudança de grupo em todo quartil. Isso é artefato de coleta, não IA.
   A flag `coleta_atipica` do IDP (origens 2020T2–2021T2) não cobre 2020T1 nem 2021T3, que também caem.
2. **Sem a janela, quase não há diferencial.** Mudar de grande grupo sobe +0,80 p.p. em Q4 e +0,67 p.p.
   em Q1. A saída para o desemprego cai em todos os quartis (−1,5 p.p. em Q1, −0,8 p.p. em Q4), o que é o ciclo.
3. **Tendências paralelas (série E).** A diferença Q4 − Q1 na mudança de grupo é 5,7 p.p. em média no pré
   (entre 5,2 e 6,0) e 5,8 p.p. no pós (entre 4,8 e 6,8). Não há divergência antes de 2023, e o nível pós
   fica dentro da faixa do pré.
4. **Direção (tabela D).** Entre quem muda de grupo, a distribuição mais/igual/menos exposta quase não se
   move (menos de 1,3 p.p. em qualquer quartil). Q1 só pode subir e Q4 só pode descer: leia a diferença
   pós − pré, não o nível.
5. 19 COD (1,1% do peso) ficam sem AIOE; a lista está em `cod_sem_aioe.csv`.

## DiD: o ponto para levar ao Danny

O viés clássico do TWFE vem da adoção escalonada, que não é o caso aqui: todos são "tratados" na mesma
data. O risco é outro. O tratamento é contínuo (intensidade do AIOE), e isso exige uma versão mais forte
de tendências paralelas, discutida por Callaway, Goodman-Bacon e Sant'Anna (2024). Vale levantar isso
junto com o event study.

## Tópico 3: narrativa do dashboard

1. **A pergunta:** exposição não é adoção.
2. **Quem está exposto:** mapa dos quartis (`quem_esta_exposto` no JSON).
3. **O que Humlum e Vestergaard esperam:** o ajuste aparece primeiro na mobilidade, não no salário.
4. **O que os dados mostram:** tabelas A, B e D e o Sankey.
5. **Por que ainda não é causal:** série E, pré-tendência e a quebra da coleta telefônica.
