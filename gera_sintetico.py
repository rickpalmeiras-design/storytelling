"""Gera um painel PNADC sintético para testar painel_storytelling.py.

Imita o rodízio da PNADC (cada domicílio fica cinco trimestres) e planta os
problemas que a auditoria precisa achar: duplicatas id x trimestre, sexo
trocado, idade incoerente, entrevistas puladas, COD fora do crosswalk e erro
de codificação no nível de 4 dígitos. No pós, as ocupações mais expostas
ganham um pouco mais de mobilidade entre grandes grupos.

    python gera_sintetico.py            # grava em saidas/sintetico/
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SAIDA = Path("saidas/sintetico")
SEMENTE = 1895
INICIO, FIM = 2019 * 4, 2025 * 4 + 2  # 2019T1 a 2025T3
ENTRADAS_POR_TRIMESTRE = 1500
CHOQUE = 2022 * 4 + 3  # 2022T4


def main():
    rng = np.random.default_rng(SEMENTE)
    SAIDA.mkdir(parents=True, exist_ok=True)

    # 60 COD de 4 dígitos, com AIOE crescendo do grupo 9 para o grupo 2.
    base_grupo = {"1": 1.0, "2": 1.4, "3": 0.8, "4": 1.1, "5": -0.3, "6": -1.2, "7": -0.8, "8": -0.6, "9": -1.0}
    cods, aioe = [], []
    for g, mu in base_grupo.items():
        for k in range(7 if g != "1" else 4):
            cods.append(f"{g}{k + 1:02d}{rng.integers(1, 9)}")
            aioe.append(mu + rng.normal(0, 0.35))
    cods, aioe = np.array(cods), np.array(aioe)
    pd.DataFrame({"cod": cods, "aioe": aioe.round(4)}).to_csv(SAIDA / "exposicao_cod.csv", index=False)
    fora_do_crosswalk = np.array(["0110", "5168", "9999"])
    grupo_de = np.array([c[0] for c in cods])
    pop_cods = np.concatenate([cods, fora_do_crosswalk])
    pop_p = np.concatenate([np.full(len(cods), 1.0), [0.2, 0.4, 0.1]])
    pop_p /= pop_p.sum()
    aioe_de = dict(zip(cods, aioe))

    linhas = []
    pid = 0
    for entrada in range(INICIO - 4, FIM + 1):
        n = ENTRADAS_POR_TRIMESTRE
        sexo = rng.choice(["1", "2"], n)
        idade = rng.integers(18, 62, n)
        peso = rng.gamma(4, 60, n)
        cond = rng.choice(["ocupado", "desocupado", "fora"], n, p=[0.62, 0.06, 0.32])
        cod = np.where(cond == "ocupado", rng.choice(pop_cods, n, p=pop_p), None)
        for i in range(n):
            pid += 1
            c, oc = cond[i], cod[i]
            for visita in range(1, 6):
                t = entrada + visita - 1
                if visita > 1:
                    if rng.random() < 0.07:  # atrito definitivo
                        break
                    pos = t > CHOQUE
                    if c == "ocupado":
                        a = aioe_de.get(oc, 0.0)
                        p_muda = 0.06 + (0.03 * max(a, 0) if pos else 0.0)
                        u = rng.random()
                        if u < 0.03:
                            c, oc = "desocupado", None
                        elif u < 0.07:
                            c, oc = "fora", None
                        elif u < 0.07 + p_muda:
                            oc = rng.choice(cods)
                        elif rng.random() < 0.10:  # erro de codificação no mesmo grande grupo
                            oc = rng.choice(cods[grupo_de == oc[0]]) if oc[0] in base_grupo else oc
                    else:
                        u = rng.random()
                        if u < (0.25 if c == "desocupado" else 0.05):
                            c, oc = "ocupado", rng.choice(pop_cods, p=pop_p)
                        elif u < 0.35:
                            c = "fora" if c == "desocupado" else "desocupado"
                if t < INICIO or t > FIM:
                    continue
                if rng.random() < 0.015:  # entrevista pulada
                    continue
                linhas.append((f"P{pid:07d}", t // 4, t % 4 + 1, visita, sexo[i], idade[i] + (visita - 1) // 4,
                               c, oc, round(peso[i], 2)))

    df = pd.DataFrame(linhas, columns=["id_pessoa", "ano", "trimestre", "visita", "sexo", "idade",
                                       "condicao", "cod", "peso"])
    # Erros de pareamento plantados
    idx = rng.choice(len(df), 400, replace=False)
    df.loc[idx[:200], "sexo"] = np.where(df.loc[idx[:200], "sexo"] == "1", "2", "1")
    df.loc[idx[200:], "idade"] = df.loc[idx[200:], "idade"] + rng.choice([-5, 7], 200)
    df = pd.concat([df, df.sample(150, random_state=SEMENTE)], ignore_index=True)
    df.to_parquet(SAIDA / "painel_sintetico.parquet", index=False)
    print(f"{len(df):,} linhas, {df['id_pessoa'].nunique():,} pessoas -> {SAIDA}/")


if __name__ == "__main__":
    main()
