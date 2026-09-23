"""Auditoria do painel PNADC e fluxos ocupacionais por exposição à IA.

Cobre os tópicos 1 e 2 da reunião e grava o `dashboard_data.json` que alimenta
o HTML do tópico 3.

Tópico 1 (auditoria) -> auditoria.md
    duplicatas id x trimestre, sexo e idade inconsistentes no mesmo id, saltos
    entre entrevistas, retenção da 1a à 5a visita, ocupados sem AIOE (com os COD
    fora do crosswalk) e composição pré/pós.

Tópico 2 (para onde as pessoas vão), sempre a partir de quem está ocupado na origem:
    A  destino no trimestre seguinte por quartil de exposição, pré vs pós, com a
       diferença em p.p.
    B  para qual grande grupo COD vão os que mudam de grupo
    D  se a migração é para ocupações mais ou menos expostas
    E  série trimestral Q4 vs Q1 (primeiro teste visual de tendências paralelas)
    Sankey dos fluxos entre grandes grupos

Decisões embutidas:
    * 2022T4 fica fora: o ChatGPT saiu em 30/11/2022, então o trimestre é
      parcialmente tratado. Sai todo par que toca 2022T4, na origem ou no destino.
    * Os quartis de exposição são fixados na distribuição do pré, ponderada
      pelos ocupados. O pós não mexe nos cortes.
    * Só entram pares de trimestres consecutivos: um salto de dois trimestres
      não conta como transição.
    * A mobilidade é medida no grande grupo COD (1 dígito). No nível de 4
      dígitos, o erro de codificação entre entrevistas infla a mobilidade.
    * A janela de coleta telefônica (origens 2020T1 a 2021T3) sai do pré. Nela
      a mudança de grupo cai à metade porque a ocupação tende a ser repetida
      entre entrevistas. O script detecta a quebra e avisa se a janela
      configurada não a cobre.

Dois formatos de entrada:
    "individuos"  painel longo, uma linha por pessoa x trimestre (id, trimestre,
                  visita, sexo, idade, condição, COD, peso). Todas as checagens
                  do tópico 1 rodam.
    "pares"       painel de transições já pareado, como
                  IDP/data/processed/pnadc_transicoes.parquet (células por
                  origem x destino, com peso_total). As checagens por id foram
                  feitas no pareamento do BigQuery, então o script informa a
                  taxa de pareamento no lugar de sexo, idade, saltos e retenção.

Uso:
    python painel_storytelling.py                        # usa o CONFIG abaixo
    python painel_storytelling.py --formato pares \\
        --painel ../IDP/data/processed/pnadc_transicoes.parquet \\
        --exposicao ../IDP/data/interim/exposicao_cod.parquet --saida saidas/pnadc_real
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# CONFIG: no painel real, em geral basta ajustar os nomes de colunas.
# ---------------------------------------------------------------------------
CONFIG = {
    "formato": "individuos",  # "individuos" ou "pares"
    "painel": "saidas/sintetico/painel_sintetico.parquet",
    "exposicao": "saidas/sintetico/exposicao_cod.csv",
    "saida": "saidas/sintetico",
    # Tratamento
    "trimestre_parcial": "2022T4",  # fica fora
    "ultimo_pre": "2022T3",  # destino <= 2022T3
    "primeiro_pos": "2023T1",  # origem >= 2023T1
    # Coleta telefônica da pandemia: a mudança de ocupação despenca porque o COD
    # tende a ser repetido. Trimestres de ORIGEM da janela saem do pré; a versão
    # com eles fica como sensibilidade (A_sensibilidade_com_janela_atipica).
    "janela_atipica": ["2020T1", "2021T3"],  # origem, inclusive
    "excluir_janela_atipica": True,
    # Colunas do painel longo (formato "individuos")
    "col_individuos": {
        "id": "id_pessoa",
        "ano": "ano",
        "trimestre": "trimestre",
        "visita": "visita",  # None se não existir
        "sexo": "sexo",
        "idade": "idade",
        "condicao": "condicao",
        "cod": "cod",
        "peso": "peso",
    },
    # Valores da coluna de condição (formato "individuos")
    "valores_condicao": {
        "ocupado": "ocupado",
        "desocupado": "desocupado",
        "fora": "fora",
    },
    # Colunas do painel de pares (formato "pares", padrão do IDP)
    "col_pares": {
        "ano": "ano",  # trimestre de origem
        "trimestre": "trimestre",
        "cod_origem": "cod_origem",
        "cod_destino": "cod_destino",
        "condicao_destino": "condicao_destino",
        "pareado": "pareado",
        "peso": "peso_total",
        "n": "n",
        "n_chave_duplicada": "n_chave_duplicada",
    },
    "valores_condicao_destino": {
        "ocupado": "ocupado",
        "desocupado": "desocupado",
        "fora": "inativo",
    },
    # Arquivo de exposição: uma linha por COD de 4 dígitos
    "col_exposicao": {"cod": "cod", "aioe": "aioe"},
    # Limiares dos alertas automáticos
    "alertas": {
        "sexo_inconsistente": 0.005,  # fração de ids
        "idade_inconsistente": 0.01,
        "saltos": 0.01,
        "peso_sem_aioe": 0.05,  # fração do peso dos ocupados
        "composicao_pp": 3.0,  # mudança pré->pós em p.p.
        "pareamento_minimo": 0.70,
        "quebra_mobilidade": 0.30,  # desvio relativo à mediana da série de mudança de grupo
    },
}

GRANDES_GRUPOS = {
    "0": "Forças armadas, policiais e bombeiros militares",
    "1": "Diretores e gerentes",
    "2": "Profissionais das ciências e intelectuais",
    "3": "Técnicos e profissionais de nível médio",
    "4": "Apoio administrativo",
    "5": "Serviços, vendedores do comércio e mercados",
    "6": "Qualificados da agropecuária, florestais, caça e pesca",
    "7": "Operários, artesãos da construção e ofícios mecânicos",
    "8": "Operadores de instalações e máquinas e montadores",
    "9": "Ocupações elementares",
}
DESTINOS = ["mesmo_grupo", "outro_grupo", "desocupado", "fora_da_forca"]
ROTULO_DESTINO = {
    "mesmo_grupo": "Mesmo grande grupo",
    "outro_grupo": "Outro grande grupo",
    "desocupado": "Desocupado",
    "fora_da_forca": "Fora da força de trabalho",
}
QUARTIS = ["Q1", "Q2", "Q3", "Q4"]


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def periodo(rotulo: str) -> int:
    """'2022T4' -> índice trimestral contínuo."""
    ano, tri = rotulo.upper().split("T")
    return int(ano) * 4 + int(tri) - 1


def rotulo(p: int) -> str:
    return f"{p // 4}T{p % 4 + 1}"


def ler(caminho: str | Path) -> pd.DataFrame:
    caminho = Path(caminho)
    if caminho.suffix == ".parquet":
        return pd.read_parquet(caminho)
    return pd.read_csv(caminho, dtype=str)


def cod4(serie: pd.Series) -> pd.Series:
    s = serie.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    return s.where(s.isna() | (s == ""), s.str.zfill(4)).replace("", pd.NA)


def _b(serie: pd.Series) -> np.ndarray:
    """Booleano do pandas (com NA) -> ndarray para np.select."""
    return serie.fillna(False).to_numpy(dtype=bool)


def quantil_ponderado(x: np.ndarray, w: np.ndarray, qs) -> list[float]:
    ordem = np.argsort(x)
    x, w = x[ordem], w[ordem]
    acum = (np.cumsum(w) - 0.5 * w) / w.sum()
    return [float(np.interp(q, acum, x)) for q in qs]


def shares(df: pd.DataFrame, por: list[str], coluna: str, categorias=None) -> pd.DataFrame:
    """Participação ponderada de cada categoria de `coluna` dentro de `por`."""
    g = df.groupby(por + [coluna], observed=True).agg(peso=("peso", "sum"), n=("n", "sum"))
    g = g.reset_index()
    tot = g.groupby(por, observed=True)[["peso", "n"]].transform("sum")
    g["share"] = g["peso"] / tot["peso"]
    g["n_celula"] = tot["n"]
    if categorias is not None:
        idx = pd.MultiIndex.from_product(
            [sorted(g[c].dropna().unique()) for c in por] + [categorias], names=por + [coluna]
        )
        g = g.set_index(por + [coluna]).reindex(idx).reset_index()
        g["share"] = g["share"].fillna(0.0)
        g["peso"] = g["peso"].fillna(0.0)
        g["n"] = g["n"].fillna(0)
        g["n_celula"] = g.groupby(por)["n_celula"].transform("max")
    return g


def diferenca_pp(tab: pd.DataFrame, chaves: list[str]) -> pd.DataFrame:
    w = tab.pivot_table(index=chaves, columns="periodo", values="share", aggfunc="first")
    n = tab.pivot_table(index=chaves, columns="periodo", values="n_celula", aggfunc="first")
    out = pd.DataFrame(
        {
            "pre": w.get("pre"),
            "pos": w.get("pos"),
            "n_pre": n.get("pre"),
            "n_pos": n.get("pos"),
        }
    )
    out["pre"] *= 100
    out["pos"] *= 100
    out["dif_pp"] = out["pos"] - out["pre"]
    return out.reset_index()


# ---------------------------------------------------------------------------
# Leitura e construção dos pares
# ---------------------------------------------------------------------------
def ler_exposicao(cfg) -> pd.Series:
    c = cfg["col_exposicao"]
    ex = ler(cfg["exposicao"])
    ex = pd.DataFrame({"cod": cod4(ex[c["cod"]]), "aioe": pd.to_numeric(ex[c["aioe"]], errors="coerce")})
    ex = ex.dropna().drop_duplicates("cod")
    return ex.set_index("cod")["aioe"]


def pares_de_individuos(cfg, auditoria: dict) -> pd.DataFrame:
    c = cfg["col_individuos"]
    v = cfg["valores_condicao"]
    bruto = ler(cfg["painel"])
    df = pd.DataFrame(
        {
            "id": bruto[c["id"]].astype(str),
            "t": pd.to_numeric(bruto[c["ano"]]).astype(int) * 4 + pd.to_numeric(bruto[c["trimestre"]]).astype(int) - 1,
            "sexo": bruto[c["sexo"]].astype(str),
            "idade": pd.to_numeric(bruto[c["idade"]], errors="coerce"),
            "condicao": bruto[c["condicao"]].astype(str),
            "cod": cod4(bruto[c["cod"]]),
            "peso": pd.to_numeric(bruto[c["peso"]], errors="coerce"),
        }
    )
    if c.get("visita") and c["visita"] in bruto:
        df["visita"] = pd.to_numeric(bruto[c["visita"]], errors="coerce")
    mapa = {v["ocupado"]: "ocupado", v["desocupado"]: "desocupado", v["fora"]: "fora"}
    df["condicao"] = df["condicao"].map(mapa)
    auditoria.update(auditar_individuos(df, cfg))

    # Duplicatas id x trimestre não pareiam: saem dos dois lados.
    dup = df.duplicated(["id", "t"], keep=False)
    df = df.loc[~dup].sort_values(["id", "t"])
    prox = df.groupby("id").shift(-1)
    consecutivo = (prox["t"] - df["t"]) == 1
    origem = df["condicao"] == "ocupado"
    pares = pd.DataFrame(
        {
            "t": df["t"],
            "cod_origem": df["cod"],
            "cod_destino": prox["cod"],
            "cond_destino": prox["condicao"],
            "peso": df["peso"],
            "n": 1,
        }
    )
    auditoria["pares"] = {
        "origens_ocupadas": int(origem.sum()),
        "com_entrevista_seguinte_consecutiva": int((origem & consecutivo).sum()),
        "descartadas_por_salto": int((origem & prox["t"].notna() & ~consecutivo).sum()),
    }
    return pares.loc[origem & consecutivo & pares["cond_destino"].notna()].reset_index(drop=True)


def pares_de_pares(cfg, auditoria: dict) -> pd.DataFrame:
    c = cfg["col_pares"]
    v = cfg["valores_condicao_destino"]
    bruto = ler(cfg["painel"])
    t = pd.to_numeric(bruto[c["ano"]]).astype(int) * 4 + pd.to_numeric(bruto[c["trimestre"]]).astype(int) - 1
    peso = pd.to_numeric(bruto[c["peso"]], errors="coerce")
    n = pd.to_numeric(bruto[c["n"]]).fillna(1) if c.get("n") in bruto else pd.Series(1, index=bruto.index)
    pareado = bruto[c["pareado"]].fillna(False).astype(bool)
    mapa = {v["ocupado"]: "ocupado", v["desocupado"]: "desocupado", v["fora"]: "fora"}
    pares = pd.DataFrame(
        {
            "t": t,
            "cod_origem": cod4(bruto[c["cod_origem"]]),
            "cod_destino": cod4(bruto[c["cod_destino"]]),
            "cond_destino": bruto[c["condicao_destino"]].map(mapa),
            "peso": peso,
            "n": n,
        }
    )
    auditoria.update(auditar_pares(pares, pareado, bruto, cfg))
    return pares.loc[pareado & pares["cond_destino"].notna()].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Tópico 1: auditoria
# ---------------------------------------------------------------------------
def auditar_individuos(df: pd.DataFrame, cfg) -> dict:
    lim = cfg["alertas"]
    ids = df["id"].nunique()
    dup = df.duplicated(["id", "t"], keep=False)
    unico = df.loc[~dup].sort_values(["id", "t"])

    sexo_inc = unico.groupby("id")["sexo"].nunique() > 1
    idade = unico.dropna(subset=["idade"])
    g = idade.groupby("id")["idade"]
    amplitude = g.max() - g.min()
    recua = g.diff().lt(0).groupby(idade["id"]).any()
    # Cinco entrevistas cobrem 12 meses: a idade avança no máximo 2 anos.
    idade_inc = (amplitude > 2) | recua.reindex(amplitude.index, fill_value=False)

    passo = unico.groupby("id")["t"].diff()
    ids_com_salto = unico.loc[passo > 1, "id"].nunique()

    retencao = None
    if "visita" in unico:
        primeira = unico.groupby("id")["visita"].min()
        coorte = primeira.index[primeira == 1]
        vis = unico.loc[unico["id"].isin(coorte)]
        base = len(coorte)
        retencao = [
            {"visita": int(k), "ids": int(vis.loc[vis["visita"] == k, "id"].nunique()),
             "pct": round(100 * vis.loc[vis["visita"] == k, "id"].nunique() / base, 2) if base else None}
            for k in range(1, 6)
        ]

    out = {
        "formato": "individuos",
        "linhas": int(len(df)),
        "ids": int(ids),
        "duplicatas_id_trimestre": {"linhas": int(dup.sum()), "ids": int(df.loc[dup, "id"].nunique())},
        "sexo_inconsistente": {"ids": int(sexo_inc.sum()), "frac": float(sexo_inc.mean())},
        "idade_inconsistente": {"ids": int(idade_inc.sum()), "frac": float(idade_inc.mean())},
        "saltos": {
            "transicoes_com_salto": int((passo > 1).sum()),
            "ids": int(ids_com_salto),
            "frac": float(ids_com_salto / ids) if ids else 0.0,
        },
        "retencao_visitas": retencao,
    }
    alertas = []
    if out["duplicatas_id_trimestre"]["linhas"]:
        alertas.append(f"{out['duplicatas_id_trimestre']['linhas']} linhas duplicadas em id x trimestre "
                       f"({out['duplicatas_id_trimestre']['ids']} ids). Elas saem do pareamento.")
    if out["sexo_inconsistente"]["frac"] > lim["sexo_inconsistente"]:
        alertas.append(f"Sexo muda dentro do mesmo id em {100 * out['sexo_inconsistente']['frac']:.2f}% dos ids: "
                       "sinal de pareamento errado.")
    if out["idade_inconsistente"]["frac"] > lim["idade_inconsistente"]:
        alertas.append(f"Idade recua ou avança mais de 2 anos em {100 * out['idade_inconsistente']['frac']:.2f}% "
                       "dos ids: sinal de pareamento errado.")
    if out["saltos"]["frac"] > lim["saltos"]:
        alertas.append(f"{100 * out['saltos']['frac']:.2f}% dos ids pulam ao menos um trimestre. "
                       "Esses saltos não contam como transição.")
    out["alertas"] = alertas
    return out


def auditar_pares(pares: pd.DataFrame, pareado: pd.Series, bruto: pd.DataFrame, cfg) -> dict:
    lim = cfg["alertas"]
    c = cfg["col_pares"]
    tmp = pares.assign(pareado=pareado)
    taxa = (
        tmp.assign(pp=tmp["peso"] * tmp["pareado"])
        .groupby("t")[["pp", "peso"]].sum()
        .assign(taxa=lambda d: d["pp"] / d["peso"])
    )
    dup = int(pd.to_numeric(bruto[c["n_chave_duplicada"]]).fillna(0).sum()) if c.get("n_chave_duplicada") in bruto else None
    out = {
        "formato": "pares",
        "celulas": int(len(pares)),
        "origens_ocupadas": int(pares["n"].sum()),
        "pares_encontrados": int(pares.loc[pareado, "n"].sum()),
        "duplicatas_id_trimestre": {"linhas": dup, "ids": None},
        "sexo_inconsistente": None,
        "idade_inconsistente": None,
        "saltos": None,
        "retencao_visitas": None,
        "taxa_pareamento": [
            {"trimestre": rotulo(int(t)), "taxa": round(float(r.taxa), 4)} for t, r in taxa.iterrows()
        ],
        "nota": "No formato de pares, sexo, nascimento, visita seguinte e trimestre seguinte já foram "
                "exigidos no pareamento (BigQuery). Chave duplicada não pareia. Aqui entram a taxa de "
                "pareamento e as duplicatas registradas.",
    }
    alertas = []
    if dup:
        alertas.append(f"{dup} registros com chave duplicada no trimestre ficaram fora do pareamento.")
    baixos = taxa.loc[taxa["taxa"] < lim["pareamento_minimo"]]
    if len(baixos):
        alertas.append(
            "Pareamento abaixo de {:.0f}% em: {}.".format(
                100 * lim["pareamento_minimo"], ", ".join(rotulo(int(t)) for t in baixos.index)
            )
        )
    out["alertas"] = alertas
    return out


def auditar_exposicao(pares: pd.DataFrame, cfg) -> tuple[dict, pd.DataFrame]:
    sem = pares.loc[pares["aioe_origem"].isna()]
    cods = (
        sem.groupby("cod_origem", dropna=False)
        .agg(peso=("peso", "sum"), n=("n", "sum"))
        .sort_values("peso", ascending=False)
        .reset_index()
    )
    cods["pct_peso_ocupados"] = 100 * cods["peso"] / pares["peso"].sum()
    frac = float(sem["peso"].sum() / pares["peso"].sum())
    out = {
        "frac_peso_sem_aioe": frac,
        "n_sem_aioe": int(sem["n"].sum()),
        "cods_fora_do_crosswalk": [
            {"cod": None if pd.isna(r.cod_origem) else str(r.cod_origem), "n": int(r.n),
             "pct_peso": round(float(r.pct_peso_ocupados), 3)}
            for r in cods.itertuples()
        ],
        "alertas": [],
    }
    if frac > cfg["alertas"]["peso_sem_aioe"]:
        out["alertas"].append(f"{100 * frac:.2f}% do peso dos ocupados na origem está sem AIOE.")
    elif len(cods):
        out["alertas"].append(f"{len(cods)} COD sem AIOE ({100 * frac:.2f}% do peso). Ficam fora dos quartis.")
    return out, cods


def auditar_quebra(p: pd.DataFrame, cfg) -> tuple[dict, pd.DataFrame]:
    """Série de mudança de grande grupo entre todos os ocupados, por trimestre de origem."""
    base = p.loc[p["destino"].notna()]
    g = (
        base.assign(m=(base["destino"] == "outro_grupo") * base["peso"])
        .groupby("t")[["m", "peso"]].sum()
    )
    serie = 100 * g["m"] / g["peso"]
    mediana = serie.median()
    quebra = serie.index[(serie / mediana - 1).abs() > cfg["alertas"]["quebra_mobilidade"]]
    ini, fim = (periodo(x) for x in cfg["janela_atipica"])
    fora = [t for t in quebra if not ini <= t <= fim]
    out = {
        "mediana_pct_muda_grupo": float(mediana),
        "trimestres_com_quebra": [rotulo(int(t)) for t in quebra],
        "janela_configurada": cfg["janela_atipica"],
        "excluida_do_pre": cfg["excluir_janela_atipica"],
        "alertas": [],
    }
    if len(quebra):
        out["alertas"].append(
            "Quebra na série de mudança de grande grupo (mediana {:.1f}%) nas origens {}. "
            "Janela atípica configurada: {} a {}{}.".format(
                mediana, ", ".join(out["trimestres_com_quebra"]), *cfg["janela_atipica"],
                "" if cfg["excluir_janela_atipica"] else " (NÃO excluída do pré)")
        )
    if fora:
        out["alertas"].append("Trimestres com quebra fora da janela atípica: "
                              + ", ".join(rotulo(int(t)) for t in fora) + ".")
    tab = pd.DataFrame({"trimestre_origem": [rotulo(int(t)) for t in serie.index],
                        "pct_muda_grupo": serie.values,
                        "quebra": serie.index.isin(quebra)})
    return out, tab


def auditar_composicao(pares: pd.DataFrame, cfg) -> tuple[dict, pd.DataFrame]:
    base = pares.loc[pares["periodo"].isin(["pre", "pos"])]
    linhas = []
    for dim in ["quartil", "grupo_origem"]:
        tab = shares(base.dropna(subset=[dim]), ["periodo"], dim)
        d = diferenca_pp(tab, [dim]).rename(columns={dim: "categoria"})
        d.insert(0, "dimensao", dim)
        linhas.append(d)
    comp = pd.concat(linhas, ignore_index=True)
    lim = cfg["alertas"]["composicao_pp"]
    fortes = comp.loc[comp["dif_pp"].abs() > lim]
    out = {
        "alertas": [
            f"Composição de {r.dimensao} = {r.categoria} muda {r.dif_pp:+.1f} p.p. do pré para o pós."
            for r in fortes.itertuples()
        ]
    }
    return out, comp


# ---------------------------------------------------------------------------
# Tópico 2
# ---------------------------------------------------------------------------
def preparar(pares: pd.DataFrame, aioe: pd.Series, cfg) -> tuple[pd.DataFrame, list[float]]:
    parcial = periodo(cfg["trimestre_parcial"])
    ultimo_pre = periodo(cfg["ultimo_pre"])
    primeiro_pos = periodo(cfg["primeiro_pos"])

    p = pares.copy()
    p["aioe_origem"] = p["cod_origem"].map(aioe)
    p["aioe_destino"] = p["cod_destino"].map(aioe)
    p["grupo_origem"] = p["cod_origem"].str[0]
    p["grupo_destino"] = p["cod_destino"].where(p["cond_destino"] == "ocupado").str[0]
    p["destino"] = np.select(
        [
            _b(p["cond_destino"] == "desocupado"),
            _b(p["cond_destino"] == "fora"),
            _b(p["grupo_destino"] == p["grupo_origem"]),
        ],
        ["desocupado", "fora_da_forca", "mesmo_grupo"],
        default="outro_grupo",
    )
    # Ocupado sem COD no destino não permite dizer se mudou de grupo.
    p.loc[(p["cond_destino"] == "ocupado") & p["grupo_destino"].isna(), "destino"] = pd.NA
    toca_parcial = (p["t"] == parcial) | (p["t"] + 1 == parcial)
    ini, fim = (periodo(x) for x in cfg["janela_atipica"])
    p["atipico"] = p["t"].between(ini, fim)
    p["periodo"] = np.select(
        [_b(toca_parcial), _b(p["t"] + 1 <= ultimo_pre), _b(p["t"] >= primeiro_pos)],
        ["excluido", "pre", "pos"],
        default="excluido",
    )
    if cfg["excluir_janela_atipica"]:
        p.loc[p["atipico"] & (p["periodo"] == "pre"), "periodo"] = "atipico"
    p["trimestre"] = p["t"].map(lambda x: rotulo(int(x)))

    pre = p.loc[(p["periodo"] == "pre") & p["aioe_origem"].notna()]
    cortes = quantil_ponderado(pre["aioe_origem"].to_numpy(float), pre["peso"].to_numpy(float), [0.25, 0.5, 0.75])
    bins = [-np.inf, *cortes, np.inf]
    p["quartil"] = pd.cut(p["aioe_origem"], bins, labels=QUARTIS).astype("string")
    p["quartil_destino"] = pd.cut(p["aioe_destino"], bins, labels=QUARTIS).astype("string")
    return p, cortes


def tabela_a(p: pd.DataFrame) -> pd.DataFrame:
    base = p.loc[p["periodo"].isin(["pre", "pos"]) & p["quartil"].notna() & p["destino"].notna()]
    todos = base.assign(quartil="Todos")
    tab = shares(pd.concat([base, todos]), ["quartil", "periodo"], "destino", DESTINOS)
    return diferenca_pp(tab, ["quartil", "destino"])


def tabela_b(p: pd.DataFrame) -> pd.DataFrame:
    base = p.loc[p["periodo"].isin(["pre", "pos"]) & (p["destino"] == "outro_grupo") & p["quartil"].notna()]
    todos = base.assign(quartil="Todos")
    tab = shares(pd.concat([base, todos]), ["quartil", "periodo"], "grupo_destino", sorted(GRANDES_GRUPOS))
    out = diferenca_pp(tab, ["quartil", "grupo_destino"])
    out["nome_grupo"] = out["grupo_destino"].map(GRANDES_GRUPOS)
    return out


def tabela_d(p: pd.DataFrame) -> pd.DataFrame:
    base = p.loc[
        p["periodo"].isin(["pre", "pos"])
        & (p["destino"] == "outro_grupo")
        & p["quartil"].notna()
        & p["quartil_destino"].notna()
    ].copy()
    qo = base["quartil"].str[1].astype(int)
    qd = base["quartil_destino"].str[1].astype(int)
    base["direcao"] = np.select([_b(qd > qo), _b(qd < qo)], ["mais_exposta", "menos_exposta"], "mesmo_quartil")
    todos = base.assign(quartil="Todos")
    comb = pd.concat([base, todos])
    tab = shares(comb, ["quartil", "periodo"], "direcao", ["mais_exposta", "mesmo_quartil", "menos_exposta"])
    out = diferenca_pp(tab, ["quartil", "direcao"])
    delta = (
        comb.assign(d=comb["aioe_destino"] - comb["aioe_origem"], wd=lambda x: x["d"] * x["peso"])
        .groupby(["quartil", "periodo"])[["wd", "peso"]].sum()
    )
    delta = (delta["wd"] / delta["peso"]).unstack("periodo")
    out["delta_aioe_medio_pre"] = out["quartil"].map(delta.get("pre"))
    out["delta_aioe_medio_pos"] = out["quartil"].map(delta.get("pos"))
    return out


def tabela_e(p: pd.DataFrame) -> pd.DataFrame:
    base = p.loc[p["quartil"].isin(["Q1", "Q4"]) & p["destino"].notna()].copy()
    base["muda_grupo"] = (base["destino"] == "outro_grupo") * base["peso"]
    base["sai_emprego"] = base["destino"].isin(["desocupado", "fora_da_forca"]) * base["peso"]
    g = base.groupby(["t", "quartil"]).agg(
        muda=("muda_grupo", "sum"), sai=("sai_emprego", "sum"), peso=("peso", "sum"), n=("n", "sum")
    )
    g["pct_muda_grupo"] = 100 * g["muda"] / g["peso"]
    g["pct_sai_emprego"] = 100 * g["sai"] / g["peso"]
    w = g[["pct_muda_grupo", "pct_sai_emprego", "n"]].unstack("quartil")
    out = pd.DataFrame(
        {
            "trimestre_origem": [rotulo(int(t)) for t in w.index],
            "muda_grupo_Q1": w[("pct_muda_grupo", "Q1")].values,
            "muda_grupo_Q4": w[("pct_muda_grupo", "Q4")].values,
            "sai_emprego_Q1": w[("pct_sai_emprego", "Q1")].values,
            "sai_emprego_Q4": w[("pct_sai_emprego", "Q4")].values,
            "n_Q1": w[("n", "Q1")].values,
            "n_Q4": w[("n", "Q4")].values,
        }
    )
    out["dif_muda_grupo_Q4_Q1"] = out["muda_grupo_Q4"] - out["muda_grupo_Q1"]
    out["dif_sai_emprego_Q4_Q1"] = out["sai_emprego_Q4"] - out["sai_emprego_Q1"]
    per = p.drop_duplicates("t").set_index("t")["periodo"]
    out["periodo"] = [per.get(int(t)) for t in w.index]
    return out


def tabela_sankey(p: pd.DataFrame) -> pd.DataFrame:
    base = p.loc[p["periodo"].isin(["pre", "pos"]) & p["destino"].notna()].copy()
    base["alvo"] = np.select(
        [_b(base["destino"] == "desocupado"), _b(base["destino"] == "fora_da_forca")],
        ["Desocupado", "Fora da força"],
        default="G" + base["grupo_destino"].fillna(""),
    )
    base["fonte"] = "G" + base["grupo_origem"]
    g = base.groupby(["periodo", "fonte", "alvo"]).agg(peso=("peso", "sum"), n=("n", "sum")).reset_index()
    g["pct_da_origem"] = 100 * g["peso"] / g.groupby(["periodo", "fonte"])["peso"].transform("sum")
    g["pct_do_total"] = 100 * g["peso"] / g.groupby("periodo")["peso"].transform("sum")
    return g


def quem_esta_exposto(p: pd.DataFrame, cortes) -> dict:
    pre = p.loc[(p["periodo"] == "pre") & p["quartil"].notna()]
    comp = shares(pre, ["quartil"], "grupo_origem")
    comp["nome_grupo"] = comp["grupo_origem"].map(GRANDES_GRUPOS)
    gg = (
        pre.assign(wa=pre["aioe_origem"] * pre["peso"])
        .groupby("grupo_origem")
        .agg(wa=("wa", "sum"), peso=("peso", "sum"))
    )
    gg["aioe_medio"] = gg["wa"] / gg["peso"]
    gg["pct_ocupados"] = 100 * gg["peso"] / gg["peso"].sum()
    qg = shares(pre, ["grupo_origem"], "quartil", QUARTIS)
    return {
        "cortes_aioe": cortes,
        "quartil_por_grupo": [
            {"quartil": r.quartil, "grupo": r.grupo_origem, "nome_grupo": r.nome_grupo,
             "pct": round(100 * r.share, 3)}
            for r in comp.itertuples()
        ],
        "grupos": [
            {"grupo": g, "nome_grupo": GRANDES_GRUPOS.get(g), "aioe_medio": round(float(r.aioe_medio), 4),
             "pct_ocupados": round(float(r.pct_ocupados), 3),
             "pct_por_quartil": {q: round(100 * float(qg.loc[(qg.grupo_origem == g) & (qg.quartil == q), "share"].sum()), 2)
                                 for q in QUARTIS}}
            for g, r in gg.sort_values("aioe_medio").iterrows()
        ],
    }


# ---------------------------------------------------------------------------
# Saídas
# ---------------------------------------------------------------------------
def fmt(x, casas=1):
    return "" if pd.isna(x) else f"{x:.{casas}f}"


def md_tabela(df: pd.DataFrame) -> str:
    cab = "| " + " | ".join(map(str, df.columns)) + " |"
    sep = "| " + " | ".join("---" for _ in df.columns) + " |"
    linhas = ["| " + " | ".join(str(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join([cab, sep, *linhas])


def escrever_auditoria(caminho: Path, aud: dict, exp: dict, comp: pd.DataFrame, p: pd.DataFrame, cortes, cfg):
    alertas = (aud.get("alertas", []) + aud["quebra"]["alertas"] + exp["alertas"]
               + aud.get("composicao", {}).get("alertas", []))
    L = [
        "# Auditoria do painel",
        "",
        f"Gerado em {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC a partir de `{cfg['painel']}` "
        f"(formato `{aud['formato']}`).",
        "",
        "## Alertas",
        "",
        *([f"- ⚠️ {a}" for a in alertas] or ["- Nenhum alerta."]),
        "",
        "## Decisões embutidas",
        "",
        f"- **{cfg['trimestre_parcial']} fica fora.** O ChatGPT saiu em 30/11/2022, então o trimestre é "
        "parcialmente tratado. Sai todo par com origem ou destino nesse trimestre.",
        f"- **Pré** = pares com destino até {cfg['ultimo_pre']}. **Pós** = pares com origem a partir de "
        f"{cfg['primeiro_pos']}.",
        "- **Quartis de exposição fixados no pré** (AIOE da ocupação de origem, ponderado pelos ocupados). "
        "Cortes: " + ", ".join(f"{c:.3f}" for c in cortes) + ".",
        "- **Só pares de trimestres consecutivos.** Um salto de dois trimestres não conta como transição.",
        "- **Mobilidade no grande grupo COD (1 dígito)**, para não inflar a mobilidade com erro de "
        "codificação entre entrevistas.",
        f"- **Janela de coleta atípica** (origens {cfg['janela_atipica'][0]} a {cfg['janela_atipica'][1]}): "
        + ("excluída do pré; a tabela A com ela fica em `A_sensibilidade_com_janela_atipica.csv`."
           if cfg["excluir_janela_atipica"] else "mantida no pré."),
        "",
        "## Integridade do painel",
        "",
    ]
    if aud["formato"] == "individuos":
        d = aud["duplicatas_id_trimestre"]
        L += [
            f"- Linhas: {aud['linhas']:,}; ids: {aud['ids']:,}.",
            f"- Duplicatas id × trimestre: {d['linhas']:,} linhas em {d['ids']:,} ids.",
            f"- Sexo inconsistente no mesmo id: {aud['sexo_inconsistente']['ids']:,} ids "
            f"({100 * aud['sexo_inconsistente']['frac']:.2f}%).",
            f"- Idade inconsistente no mesmo id (recua ou avança mais de 2 anos): "
            f"{aud['idade_inconsistente']['ids']:,} ids ({100 * aud['idade_inconsistente']['frac']:.2f}%).",
            f"- Saltos entre entrevistas: {aud['saltos']['transicoes_com_salto']:,} transições em "
            f"{aud['saltos']['ids']:,} ids ({100 * aud['saltos']['frac']:.2f}%).",
            f"- Origens ocupadas: {aud['pares']['origens_ocupadas']:,}; com entrevista seguinte consecutiva: "
            f"{aud['pares']['com_entrevista_seguinte_consecutiva']:,}; descartadas por salto: "
            f"{aud['pares']['descartadas_por_salto']:,}.",
            "",
        ]
        if aud["retencao_visitas"]:
            L += [
                "### Retenção da 1ª à 5ª visita",
                "",
                "Coorte: ids observados pela primeira vez na 1ª visita.",
                "",
                md_tabela(pd.DataFrame(aud["retencao_visitas"]).rename(
                    columns={"visita": "Visita", "ids": "Ids", "pct": "% da coorte"})),
                "",
            ]
    else:
        L += [
            f"- Células: {aud['celulas']:,}; origens ocupadas: {aud['origens_ocupadas']:,}; "
            f"pares encontrados: {aud['pares_encontrados']:,}.",
            f"- Registros com chave duplicada no trimestre (não pareados): {aud['duplicatas_id_trimestre']['linhas']}.",
            f"- {aud['nota']}",
            "",
            "### Taxa de pareamento por trimestre de origem",
            "",
            md_tabela(pd.DataFrame(aud["taxa_pareamento"]).assign(
                taxa=lambda d: (100 * d["taxa"]).map(lambda x: f"{x:.1f}%")).rename(
                columns={"trimestre": "Trimestre", "taxa": "Pareados (peso)"})),
            "",
        ]
    L += [
        "## Ocupados sem AIOE",
        "",
        f"{100 * exp['frac_peso_sem_aioe']:.2f}% do peso dos ocupados na origem "
        f"({exp['n_sem_aioe']:,} observações) está sem AIOE.",
        "",
    ]
    if exp["cods_fora_do_crosswalk"]:
        L += [
            "COD fora do crosswalk:",
            "",
            md_tabela(pd.DataFrame(exp["cods_fora_do_crosswalk"]).rename(
                columns={"cod": "COD", "n": "Obs.", "pct_peso": "% do peso"})),
            "",
        ]
    q = aud["quebra"]
    L += [
        "## Quebra da coleta telefônica",
        "",
        f"Mudança de grande grupo entre todos os ocupados, por trimestre de origem. Mediana: "
        f"{q['mediana_pct_muda_grupo']:.1f}%. Trimestres a mais de "
        f"{100 * cfg['alertas']['quebra_mobilidade']:.0f}% da mediana: "
        f"{', '.join(q['trimestres_com_quebra']) or 'nenhum'}.",
        "",
    ]
    per = p.groupby("periodo")["n"].sum()
    L += [
        "## Composição pré/pós",
        "",
        f"Pares por período: pré {int(per.get('pre', 0)):,}; pós {int(per.get('pos', 0)):,}; "
        f"janela atípica {int(per.get('atipico', 0)):,}; excluídos por {cfg['trimestre_parcial']} "
        f"{int(per.get('excluido', 0)):,}.",
        "",
        md_tabela(comp.assign(
            categoria=lambda d: np.where(d["dimensao"] == "grupo_origem",
                                         d["categoria"].astype(str) + " " + d["categoria"].map(GRANDES_GRUPOS).fillna(""),
                                         d["categoria"]),
            pre=lambda d: d["pre"].map(fmt), pos=lambda d: d["pos"].map(fmt), dif_pp=lambda d: d["dif_pp"].map(fmt),
        )[["dimensao", "categoria", "pre", "pos", "dif_pp"]].rename(
            columns={"dimensao": "Dimensão", "categoria": "Categoria", "pre": "Pré (%)", "pos": "Pós (%)",
                     "dif_pp": "Dif. (p.p.)"})),
        "",
    ]
    caminho.write_text("\n".join(L), encoding="utf-8")


def registros(df: pd.DataFrame) -> list[dict]:
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_float_dtype(df[c]):
            df[c] = df[c].round(4)
    return json.loads(df.to_json(orient="records", force_ascii=False))


SANKEY_HTML = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Fluxos entre grandes grupos</title>
<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js"></script>
<style>body{font-family:system-ui,sans-serif;margin:16px}select{font-size:1rem}</style></head>
<body><h1>Fluxos entre grandes grupos COD</h1>
<p>Ocupados na origem e situação no trimestre seguinte. Largura = peso amostral.
<label>Período <select id="per"><option value="pre">Pré</option><option value="pos">Pós</option></select></label>
<label><input type="checkbox" id="fica"> incluir quem fica no mesmo grupo</label></p>
<div id="g" style="height:720px"></div>
<script>
const D = __DADOS__;
function desenha(){
  const per = document.getElementById('per').value, fica = document.getElementById('fica').checked;
  const L = D.filter(d => d.periodo === per && (fica || d.fonte !== d.alvo));
  const nomes = [...new Set(L.map(d => d.fonte + ' (origem)').concat(L.map(d => d.alvo)))];
  const ix = n => nomes.indexOf(n);
  Plotly.react('g', [{type:'sankey', arrangement:'snap',
    node:{label:nomes, pad:12},
    link:{source:L.map(d => ix(d.fonte + ' (origem)')), target:L.map(d => ix(d.alvo)), value:L.map(d => d.peso),
          customdata:L.map(d => d.pct_da_origem.toFixed(1) + '% da origem'), hovertemplate:'%{customdata}<extra></extra>'}}],
    {margin:{l:8,r:8,t:8,b:8}});
}
document.getElementById('per').onchange = desenha; document.getElementById('fica').onchange = desenha; desenha();
</script></body></html>
"""


def executar(cfg: dict) -> dict:
    saida = Path(cfg["saida"])
    saida.mkdir(parents=True, exist_ok=True)
    aud: dict = {}
    if cfg["formato"] == "individuos":
        pares = pares_de_individuos(cfg, aud)
    elif cfg["formato"] == "pares":
        pares = pares_de_pares(cfg, aud)
    else:
        raise ValueError("formato deve ser 'individuos' ou 'pares'")

    aioe = ler_exposicao(cfg)
    p, cortes = preparar(pares, aioe, cfg)
    exp, cods = auditar_exposicao(p, cfg)
    aud["composicao"], comp = auditar_composicao(p, cfg)
    aud["quebra"], serie_quebra = auditar_quebra(p, cfg)

    a, b, d, e, s = tabela_a(p), tabela_b(p), tabela_d(p), tabela_e(p), tabela_sankey(p)
    # Sensibilidade: mesmos cortes, com a janela atípica de volta no pré.
    alt = p.copy()
    alt.loc[alt["periodo"] == "atipico", "periodo"] = "pre" if cfg["excluir_janela_atipica"] else "atipico"
    if not cfg["excluir_janela_atipica"]:
        alt.loc[alt["atipico"] & (alt["periodo"] == "pre"), "periodo"] = "atipico"
    a_sens = tabela_a(alt)
    expostos = quem_esta_exposto(p, cortes)

    escrever_auditoria(saida / "auditoria.md", aud, exp, comp, p, cortes, cfg)
    for nome, tab in {
        "A_destino_por_quartil": a,
        "A_sensibilidade_com_janela_atipica" if cfg["excluir_janela_atipica"] else "A_sensibilidade_sem_janela_atipica": a_sens,
        "serie_muda_grupo_todos": serie_quebra,
        "B_grupo_destino_dos_que_mudam": b,
        "D_direcao_exposicao": d,
        "E_serie_Q4_vs_Q1": e,
        "sankey_fluxos": s,
        "composicao_pre_pos": comp,
        "cod_sem_aioe": cods,
    }.items():
        tab.to_csv(saida / f"{nome}.csv", index=False, encoding="utf-8")
    (saida / "sankey.html").write_text(
        SANKEY_HTML.replace("__DADOS__", json.dumps(registros(s), ensure_ascii=False)), encoding="utf-8"
    )

    per = p.groupby("periodo")["n"].sum()
    dados = {
        "meta": {
            "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "fonte": str(cfg["painel"]),
            "formato": cfg["formato"],
            "trimestre_parcial_excluido": cfg["trimestre_parcial"],
            "pre": f"destino até {cfg['ultimo_pre']}",
            "pos": f"origem a partir de {cfg['primeiro_pos']}",
            "trimestres_origem": [rotulo(int(t)) for t in sorted(p["t"].unique())],
            "pares": {k: int(per.get(k, 0)) for k in ["pre", "pos", "atipico", "excluido"]},
            "janela_atipica_origem": cfg["janela_atipica"],
            "janela_atipica_excluida_do_pre": cfg["excluir_janela_atipica"],
            "cortes_quartis_aioe_pre": cortes,
            "nivel_ocupacional": "grande grupo COD (1 dígito)",
            "grandes_grupos": GRANDES_GRUPOS,
            "rotulos_destino": ROTULO_DESTINO,
        },
        "auditoria": {
            "alertas": aud.get("alertas", []) + aud["quebra"]["alertas"] + exp["alertas"] + aud["composicao"]["alertas"],
            "painel": {k: v for k, v in aud.items() if k not in ("alertas", "composicao", "quebra")},
            "quebra_coleta": aud["quebra"],
            "serie_muda_grupo_todos": registros(serie_quebra),
            "exposicao": exp,
            "composicao_pre_pos": registros(comp),
        },
        "quem_esta_exposto": expostos,
        "A_destino_por_quartil": registros(a),
        "A_sensibilidade_janela_atipica": registros(a_sens),
        "B_grupo_destino_dos_que_mudam": registros(b),
        "D_direcao_exposicao": registros(d),
        "E_serie_Q4_vs_Q1": registros(e),
        "sankey": registros(s),
    }
    (saida / "dashboard_data.json").write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    return dados


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--formato", choices=["individuos", "pares"])
    ap.add_argument("--painel")
    ap.add_argument("--exposicao")
    ap.add_argument("--saida")
    args = ap.parse_args()
    cfg = {**CONFIG, **{k: v for k, v in vars(args).items() if v}}
    dados = executar(cfg)
    print(f"Saídas em {cfg['saida']}/")
    for alerta in dados["auditoria"]["alertas"]:
        print("ALERTA:", alerta)
    a = pd.DataFrame(dados["A_destino_por_quartil"])
    print("\nA. Destino no trimestre seguinte (%), pré vs pós")
    print(a.pivot(index="destino", columns="quartil", values="dif_pp").round(2).to_string())


if __name__ == "__main__":
    main()
