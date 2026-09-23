"""Revisão da base final, estatísticas descritivas e preparação para o Diff-in-Diff.

Roda direto sobre o painel de transições do IDP (`data/processed/pnadc_transicoes.parquet`)
e sobre a exposição por COD (`data/interim/exposicao_cod.parquet`). Não altera nenhum
arquivo do IDP: tudo aqui é leitura. As decisões de amostra são as três já documentadas
em `IDP/METODOLOGIA.md` e no `storytelling/painel_storytelling.py` — este script não
inventa nenhuma nova, só as aplica de novo e explica cada uma no `quadro_resumo`.

Produz, em `saidas/dissertacao/`:
    quadro_resumo.json / .md      como o painel foi construído (tópico 1)
    descritivas_geral.json        contagens do tópico 2, pré vs pós
    matriz_transicao.csv          origem -> destino, por quartil e período
    top_ocupacoes_origem.csv      maiores ocupações de origem (COD, peso, %)
    top_ocupacoes_destino.csv     maiores ocupações de destino
    ocupacoes_exposicao.csv       ranking de ocupações por AIOE (tópico 3)
    exposicao_distribuicao.csv    histograma da exposição ponderado pelo emprego
    serie_emprego_quartil.csv     série trimestral de emprego e desfechos por quartil
    o_que_aconteceu.json          o quadro de 4 categorias + informalidade em separado
    did_variaveis.json            tratamento / período / outcome / controles / EF / unidade
    dashboard_data_v2.json        tudo junto, para o HTML

Uso:
    python base_dissertacao.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

IDP = Path("../IDP")
PAINEL = IDP / "data/processed/pnadc_transicoes.parquet"
EXPOSICAO = IDP / "data/interim/exposicao_cod.parquet"
COD_NOMES = Path("saidas/dissertacao/cod_nomes.csv")
SAIDA = Path("saidas/dissertacao")

# As mesmas três decisões de painel_storytelling.py — repetidas aqui, não redefinidas.
TRIMESTRE_PARCIAL = "2022T4"
ULTIMO_PRE = "2022T3"
PRIMEIRO_POS = "2023T1"
JANELA_ATIPICA = ("2020T1", "2021T3")  # coleta telefônica da pandemia; sai do pré
IDADE_MIN, IDADE_MAX = 18, 65  # config.yaml do IDP

GRANDES_GRUPOS = {
    "0": "Forças armadas, policiais e bombeiros militares", "1": "Diretores e gerentes",
    "2": "Profissionais das ciências e intelectuais", "3": "Técnicos e profissionais de nível médio",
    "4": "Apoio administrativo", "5": "Serviços, vendedores do comércio e mercados",
    "6": "Qualificados da agropecuária, florestais, caça e pesca",
    "7": "Operários, artesãos da construção e ofícios mecânicos",
    "8": "Operadores de instalações e máquinas e montadores", "9": "Ocupações elementares",
}
QUARTIS = ["Q1", "Q2", "Q3", "Q4"]
MIN_N_OCUPACAO = 80  # tamanho mínimo de célula para entrar no ranking de ocupações (topico 3)


def periodo_idx(rotulo: str) -> int:
    ano, tri = rotulo.upper().split("T")
    return int(ano) * 4 + int(tri) - 1


def rotulo(p: int) -> str:
    return f"{p // 4}T{p % 4 + 1}"


def cod4(serie: pd.Series) -> pd.Series:
    """Zero-preenche o COD para 4 dígitos. O parquet do IDP grava alguns códigos sem os zeros à
    esquerda (ex.: '412' em vez de '0412', todos do grande grupo 0 — forças armadas/policiais/
    bombeiros). Sem isso, `cod[0]` lê o grande grupo errado para ~0,01% das células. Mesma função
    de `painel_storytelling.py`, repetida aqui para manter este script autocontido."""
    s = serie.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    return s.where(s.isna() | (s == ""), s.str.zfill(4)).replace("", pd.NA)


def carregar() -> pd.DataFrame:
    """Lê o painel de transições tal como o IDP o construiu — sem tocar no arquivo."""
    cols = ["ano", "trimestre", "cod_origem", "cod_destino", "idade", "sexo",
            "formal_origem", "formal_destino", "ocupado_destino", "condicao_destino",
            "pareado", "peso_total", "n", "n_chave_duplicada", "n_peso_invalido",
            "aioe_origem", "aioe_destino"]
    df = pd.read_parquet(PAINEL, columns=cols)
    df = df.rename(columns={"peso_total": "peso"})
    df["cod_origem"] = cod4(df["cod_origem"])
    df["cod_destino"] = cod4(df["cod_destino"])
    df["t"] = df["ano"].astype(int) * 4 + df["trimestre"].astype(int) - 1
    return df


def preparar(df: pd.DataFrame) -> tuple[pd.DataFrame, list[float]]:
    """Aplica as três decisões e devolve o painel com período, quartil e destino classificado."""
    p = df.copy()
    p["grupo_origem"] = p["cod_origem"].str[0]
    p["grupo_destino"] = p["cod_destino"].where(p["condicao_destino"] == "ocupado").str[0]
    p["destino"] = np.select(
        [(p["condicao_destino"] == "desocupado").fillna(False).to_numpy(dtype=bool),
         (p["condicao_destino"] == "inativo").fillna(False).to_numpy(dtype=bool),
         (p["grupo_destino"] == p["grupo_origem"]).fillna(False).to_numpy(dtype=bool)],
        ["desocupado", "fora_da_forca", "mesmo_grupo"], default="outro_grupo",
    )
    p.loc[(p["condicao_destino"] == "ocupado") & p["grupo_destino"].isna(), "destino"] = pd.NA
    # Não pareado (a entrevista seguinte não foi encontrada) = sem destino, não "outro grupo".
    # np.select cairia no default errado aqui se não fosse esta linha.
    p.loc[~p["pareado"].fillna(False), "destino"] = pd.NA

    parcial, ini_at, fim_at = periodo_idx(TRIMESTRE_PARCIAL), periodo_idx(JANELA_ATIPICA[0]), periodo_idx(JANELA_ATIPICA[1])
    toca_parcial = ((p["t"] == parcial) | (p["t"] + 1 == parcial)).to_numpy(dtype=bool)
    ultimo_pre, primeiro_pos = periodo_idx(ULTIMO_PRE), periodo_idx(PRIMEIRO_POS)
    p["periodo"] = np.select(
        [toca_parcial, (p["t"] + 1 <= ultimo_pre).to_numpy(dtype=bool), (p["t"] >= primeiro_pos).to_numpy(dtype=bool)],
        ["excluido", "pre", "pos"], default="excluido",
    )
    atipico = p["t"].between(ini_at, fim_at)
    p.loc[atipico & (p["periodo"] == "pre"), "periodo"] = "atipico"

    pre = p.loc[(p["periodo"] == "pre") & p["aioe_origem"].notna()]
    x, w = pre["aioe_origem"].to_numpy(float), pre["peso"].to_numpy(float)
    ordem = np.argsort(x); x, w = x[ordem], w[ordem]
    acum = (np.cumsum(w) - 0.5 * w) / w.sum()
    cortes = [float(np.interp(q, acum, x)) for q in [0.25, 0.5, 0.75]]
    bins = [-np.inf, *cortes, np.inf]
    p["quartil"] = pd.cut(p["aioe_origem"], bins, labels=QUARTIS).astype("string")
    p["formal_para_informal"] = (p["condicao_destino"] == "ocupado") & (p["formal_origem"] == 1) & (p["formal_destino"] == 0)
    p["formal_para_informal"] = p["formal_para_informal"].where(
        p["pareado"] & (p["formal_origem"] == 1) & (p["condicao_destino"].notna())
    )
    return p, cortes


def nomes_cod() -> pd.Series:
    n = pd.read_csv(COD_NOMES, dtype=str)
    return n.set_index("grupo_base")["nome"]


def registros(df: pd.DataFrame) -> list[dict]:
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_float_dtype(df[c]):
            df[c] = df[c].round(4)
    return json.loads(df.to_json(orient="records", force_ascii=False))


# ---------------------------------------------------------------------------
# Tópico 1 — quadro-resumo da construção do painel
# ---------------------------------------------------------------------------
def quadro_resumo(df: pd.DataFrame, p: pd.DataFrame) -> dict:
    trims = sorted(df[["ano", "trimestre"]].drop_duplicates().itertuples(index=False), key=lambda r: (r.ano, r.trimestre))
    primeiro, ultimo = trims[0], trims[-1]
    cod_sem_aioe = p.loc[p["aioe_origem"].isna() & p["cod_origem"].notna()]
    formal_nulo = df["formal_origem"].isna().sum()

    return {
        "unidade_de_observacao": {
            "descricao": "Célula agregada por trimestre × UF × UPA × ocupação de origem × ocupação "
                          "de destino × covariáveis (idade, sexo, escolaridade etc.), com contagem de "
                          "observações (n) e soma de peso amostral (V1028).",
            "por_que_celula_e_nao_pessoa": "A auto-junção acontece no BigQuery e só descem células "
                          "agregadas — o projeto do IDP proíbe baixar microdado individual "
                          "(`src/common.query` recusa qualquer consulta sem agregação). Como todas as "
                          "regressoras e desfechos são constantes dentro da célula, a estimação em "
                          "células reproduz exatamente a estimação pessoa a pessoa. Por isso "
                          "'quantidade de pessoas' abaixo é a soma de peso amostral (estimativa "
                          "populacional) e a soma de n (contagem de pares na amostra), não uma "
                          "contagem de identificadores únicos — este script não tem acesso a eles.",
        },
        "fontes": {
            "pnadc": "PNAD Contínua trimestral, IBGE, via basedosdados.br_ibge_pnadc.microdados.",
            "aioe": "Felten, Raj e Seamans — AIOE, apêndice de dados em IDP/data/raw/aioe/.",
            "crosswalk": "COD (IBGE) → ISCO-08 → SOC2010, reprodução arquivada da correspondência do BLS.",
            "consolidacao": "Pareamento pessoa a pessoa no BigQuery (mesmo domicílio, número de ordem, "
                             "visita seguinte, sexo, dia/mês de nascimento iguais, ano de nascimento "
                             "com diferença ≤1, idade avançando 0–1 ano); exposição do COD é a média "
                             "dos SOC ponderada por pesos declarados no crosswalk, ignorando elos sem "
                             "valor em vez de tratá-los como zero.",
        },
        "periodo": {"primeiro_trimestre": f"{primeiro.ano}T{primeiro.trimestre}",
                     "ultimo_trimestre": f"{ultimo.ano}T{ultimo.trimestre}",
                     "n_trimestres_de_origem": len(trims)},
        "escala": {
            "celulas": int(len(df)),
            "n_pares_amostrais": int(df["n"].sum()),
            "peso_amostral_total_ocupados_origem": float(df["peso"].sum()),
            "cod_origem_distintos": int(df["cod_origem"].nunique()),
            "cod_destino_distintos": int(df["cod_destino"].nunique()),
            "grandes_grupos": 10,
        },
        "ausentes_e_inconsistencias": {
            "cod_sem_aioe": {"peso": float(cod_sem_aioe["peso"].sum()),
                              "pct_do_peso_ocupados": round(100 * cod_sem_aioe["peso"].sum() / df["peso"].sum(), 2),
                              "n_cods_distintos": int(cod_sem_aioe["cod_origem"].nunique()),
                              "nota": "Militares e um grupo de base sem correspondência no BLS ficam "
                                      "sem AIOE por desenho (METODOLOGIA.md §4); saem dos quartis."},
            "formal_origem_nulo": {"observacoes": int(formal_nulo),
                                    "nota": "Conta-própria e empregador sem CNPJ declarado ficam nulos "
                                            "em formal_origem — não viram zero (METODOLOGIA.md §3)."},
            "chave_duplicada_no_trimestre": int(df["n_chave_duplicada"].sum()),
            "peso_invalido": int(df["n_peso_invalido"].sum()),
            "taxa_de_pareamento_abaixo_de_70pct": [
                f"{int(a)}T{int(t)}" for (a, t), g in df.groupby(["ano", "trimestre"])
                if g.loc[g["pareado"], "peso"].sum() / g["peso"].sum() < 0.70
            ],
        },
        "filtros_aplicados": [
            f"Idade na PNADC entre {IDADE_MIN} e {IDADE_MAX} anos (aplicado antes deste script, na "
            "consulta do IDP — config.yaml: idade_minima_pnadc / idade_maxima_pnadc).",
            "Origem é pessoa ocupada (o painel de transições só existe a partir de quem tinha "
            "ocupação na entrevista de origem).",
            "Só pares de trimestres consecutivos entram — a auto-junção do BigQuery liga t a t+1 "
            "diretamente; um salto de dois trimestres não gera par.",
            f"{TRIMESTRE_PARCIAL} sai da análise pré/pós: o ChatGPT foi lançado em 30/11/2022, então "
            "esse trimestre é parcialmente tratado. Nenhum dado é apagado — o trimestre continua no "
            "arquivo, só não entra na comparação pré/pós.",
            f"Pré = destino até {ULTIMO_PRE}; pós = origem a partir de {PRIMEIRO_POS}.",
            f"Coleta telefônica da pandemia (origens {JANELA_ATIPICA[0]} a {JANELA_ATIPICA[1]}) sai do "
            "pré: nela a mudança de ocupação cai por artefato de coleta, não por comportamento — ver "
            "'Quebra da coleta telefônica' nas estatísticas descritivas.",
            "Quartis de AIOE fixados na distribuição do pré-choque, ponderada pelo peso amostral dos "
            "ocupados — o pós não contamina os cortes.",
            "Mobilidade ocupacional lida no grande grupo COD (1 dígito), não no código de 4 dígitos: "
            "erro de codificação entre entrevistas na PNADC infla artificialmente a mobilidade fina.",
        ],
        "alteracoes_na_base_original": "Nenhuma. Este script só lê "
            "`data/processed/pnadc_transicoes.parquet` e `data/interim/exposicao_cod.parquet` — não "
            "escreve, não sobrescreve e não recalcula nada dentro do repositório do IDP. Toda "
            "reclassificação (período, quartil, destino) é feita em memória, aqui, e documentada nesta "
            "seção e no código-fonte deste script.",
    }


# ---------------------------------------------------------------------------
# Tópico 2 — estatísticas descritivas
# ---------------------------------------------------------------------------
def descritivas(p: pd.DataFrame) -> dict:
    def bloco(sub: pd.DataFrame) -> dict:
        tot_peso, tot_n = sub["peso"].sum(), sub["n"].sum()
        obs = sub.loc[sub["destino"].notna()]
        obs_peso = obs["peso"].sum()
        def parte(mask, label):
            s = obs.loc[mask]
            return {"peso": float(s["peso"].sum()), "n": int(s["n"].sum()),
                    "pct_dos_pareados": round(100 * s["peso"].sum() / obs_peso, 2) if obs_peso else None}
        formal_base = sub.loc[sub["pareado"] & (sub["formal_origem"] == 1) & sub["condicao_destino"].notna()]
        informal_peso = formal_base.loc[formal_base["formal_para_informal"] == True, "peso"].sum()
        return {
            "empregados_na_origem": {"peso": float(tot_peso), "n": int(tot_n)},
            "pareados": {"peso": float(obs_peso), "n": int(obs["n"].sum()),
                         "pct_do_total": round(100 * obs_peso / tot_peso, 2) if tot_peso else None},
            "permaneceram_na_mesma_ocupacao": parte(obs["destino"] == "mesmo_grupo", "mesmo"),
            "mudaram_de_ocupacao": parte(obs["destino"] == "outro_grupo", "outro"),
            "sairam_do_emprego": parte(obs["destino"].isin(["desocupado", "fora_da_forca"]), "saida"),
            "ficaram_desempregados": parte(obs["destino"] == "desocupado", "desoc"),
            "sairam_da_forca_de_trabalho": parte(obs["destino"] == "fora_da_forca", "fora"),
            "migraram_para_informalidade": {
                "peso": float(informal_peso), "n": int(formal_base.loc[formal_base["formal_para_informal"] == True, "n"].sum()),
                "base": "formalmente empregados na origem, com destino observado",
                "pct_da_base": round(100 * informal_peso / formal_base["peso"].sum(), 2) if len(formal_base) else None,
            },
        }
    out = {"pre": bloco(p.loc[p["periodo"] == "pre"]), "pos": bloco(p.loc[p["periodo"] == "pos"])}
    out["entradas_na_forca_de_trabalho"] = {
        "disponivel": False,
        "motivo": "O painel de transições do IDP só existe a partir de quem estava OCUPADO na "
                  "entrevista de origem (README do IDP, 'Regras de dados'). Uma pessoa desocupada ou "
                  "fora da força que consegue um emprego não gera uma célula de origem neste arquivo, "
                  "então entradas na força de trabalho não são observáveis com os dados atuais — só "
                  "as saídas (para desemprego ou inatividade) o são. Registrado aqui para não ser "
                  "confundido com um resultado nulo.",
    }
    return out


# ---------------------------------------------------------------------------
# Matriz de transição, ocupações e distribuição da exposição
# ---------------------------------------------------------------------------
def matriz_transicao(p: pd.DataFrame) -> pd.DataFrame:
    base = p.loc[p["periodo"].isin(["pre", "pos"]) & p["destino"].notna()].copy()
    base["alvo"] = np.select(
        [(base["destino"] == "desocupado").to_numpy(), (base["destino"] == "fora_da_forca").to_numpy()],
        ["Desocupado", "Fora da força de trabalho"], default="G" + base["grupo_destino"].fillna(""),
    )
    linhas = []
    for quartil_col, quartil_val in [("quartil", None)] + [("quartil", q) for q in QUARTIS]:
        sub = base if quartil_val is None else base.loc[base["quartil"] == quartil_val]
        g = sub.groupby(["periodo", "grupo_origem", "alvo"]).agg(peso=("peso", "sum"), n=("n", "sum")).reset_index()
        g["quartil"] = quartil_val or "Todos"
        g["pct_da_origem"] = 100 * g["peso"] / g.groupby(["periodo", "grupo_origem"])["peso"].transform("sum")
        linhas.append(g)
    out = pd.concat(linhas, ignore_index=True).drop_duplicates(subset=["periodo", "grupo_origem", "alvo", "quartil"])
    return out[["quartil", "periodo", "grupo_origem", "alvo", "peso", "n", "pct_da_origem"]]


def top_ocupacoes(p: pd.DataFrame, nomes: pd.Series, lado: str, k: int = 20) -> pd.DataFrame:
    col = "cod_origem" if lado == "origem" else "cod_destino"
    sub = p.loc[p[col].notna()]
    if lado == "destino":
        sub = sub.loc[sub["condicao_destino"] == "ocupado"]
    g = sub.groupby(col).agg(peso=("peso", "sum"), n=("n", "sum")).reset_index().rename(columns={col: "cod"})
    g["nome"] = g["cod"].map(nomes)
    g["grande_grupo"] = g["cod"].str[0]
    g["nome_grande_grupo"] = g["grande_grupo"].map(GRANDES_GRUPOS)
    g["pct_do_total"] = 100 * g["peso"] / g["peso"].sum()
    return g.sort_values("peso", ascending=False).head(k).reset_index(drop=True)


def ocupacoes_exposicao(p: pd.DataFrame, nomes: pd.Series) -> pd.DataFrame:
    """Ranking de ocupações (COD, 4 dígitos) por AIOE — só o tamanho e a composição de saída de
    cada ocupação (mesmo grande grupo / outro grande grupo / desocupado / fora / informalizou).
    Mobilidade fina entre códigos de 4 dígitos não é usada como indicador (ver METODOLOGIA.md):
    aqui a ocupação de 4 dígitos é só a unidade de agregação e ranking, não a medida de mobilidade."""
    linhas = []
    for periodo in ["pre", "pos"]:
        sub = p.loc[(p["periodo"] == periodo) & p["cod_origem"].notna() & p["aioe_origem"].notna()]
        obs = sub.loc[sub["destino"].notna()]
        base_formal = sub.loc[sub["pareado"] & (sub["formal_origem"] == 1) & sub["condicao_destino"].notna()]
        g = sub.groupby("cod_origem").agg(peso=("peso", "sum"), n=("n", "sum"), aioe=("aioe_origem", "first")).reset_index()
        dest = obs.groupby(["cod_origem", "destino"])["peso"].sum().unstack(fill_value=0.0)
        for c in ["mesmo_grupo", "outro_grupo", "desocupado", "fora_da_forca"]:
            if c not in dest: dest[c] = 0.0
        dest_tot = dest.sum(axis=1)
        pct = dest.div(dest_tot, axis=0) * 100
        inf = base_formal.groupby("cod_origem").apply(
            lambda d: 100 * d.loc[d["formal_para_informal"] == True, "peso"].sum() / d["peso"].sum() if d["peso"].sum() else np.nan,
            include_groups=False)
        g = g.set_index("cod_origem")
        g["pct_mesmo_grupo"] = pct["mesmo_grupo"]; g["pct_outro_grupo"] = pct["outro_grupo"]
        g["pct_desocupado"] = pct["desocupado"]; g["pct_fora_da_forca"] = pct["fora_da_forca"]
        g["pct_informalizou"] = inf
        g["periodo"] = periodo
        linhas.append(g.reset_index().rename(columns={"cod_origem": "cod"}))
    out = pd.concat(linhas, ignore_index=True)
    out["nome"] = out["cod"].map(nomes)
    out["grande_grupo"] = out["cod"].str[0]
    out["nome_grande_grupo"] = out["grande_grupo"].map(GRANDES_GRUPOS)
    out = out[out["n"] >= MIN_N_OCUPACAO]
    return out.sort_values(["periodo", "aioe"], ascending=[True, False]).reset_index(drop=True)


def exposicao_distribuicao(p: pd.DataFrame, n_bins: int = 24) -> pd.DataFrame:
    sub = p.loc[(p["periodo"] == "pre") & p["aioe_origem"].notna()]
    lo, hi = sub["aioe_origem"].min(), sub["aioe_origem"].max()
    edges = np.linspace(lo, hi, n_bins + 1)
    sub = sub.assign(bin=pd.cut(sub["aioe_origem"], edges, include_lowest=True))
    g = sub.groupby("bin", observed=True)["peso"].sum().reset_index()
    g["centro"] = g["bin"].apply(lambda b: (b.left + b.right) / 2).astype(float)
    g["pct"] = 100 * g["peso"] / g["peso"].sum()
    return g[["centro", "peso", "pct"]]


def serie_emprego_quartil(p: pd.DataFrame) -> pd.DataFrame:
    linhas = []
    for (t, q), sub in p.loc[p["quartil"].notna()].groupby(["t", "quartil"], observed=True):
        obs = sub.loc[sub["destino"].notna()]
        obs_peso = obs["peso"].sum()
        base_formal = sub.loc[sub["pareado"] & (sub["formal_origem"] == 1) & sub["condicao_destino"].notna()]
        linhas.append({
            "trimestre_origem": rotulo(int(t)), "quartil": q, "periodo": sub["periodo"].iloc[0],
            "peso_ocupados_origem": float(sub["peso"].sum()), "n_ocupados_origem": int(sub["n"].sum()),
            "pct_mesmo_grupo": 100 * obs.loc[obs["destino"] == "mesmo_grupo", "peso"].sum() / obs_peso if obs_peso else np.nan,
            "pct_outro_grupo": 100 * obs.loc[obs["destino"] == "outro_grupo", "peso"].sum() / obs_peso if obs_peso else np.nan,
            "pct_desocupado": 100 * obs.loc[obs["destino"] == "desocupado", "peso"].sum() / obs_peso if obs_peso else np.nan,
            "pct_fora_da_forca": 100 * obs.loc[obs["destino"] == "fora_da_forca", "peso"].sum() / obs_peso if obs_peso else np.nan,
            "pct_informalizou": 100 * base_formal.loc[base_formal["formal_para_informal"] == True, "peso"].sum() / base_formal["peso"].sum() if len(base_formal) else np.nan,
        })
    return pd.DataFrame(linhas).sort_values(["quartil", "trimestre_origem"]).reset_index(drop=True)


def o_que_aconteceu(p: pd.DataFrame) -> dict:
    """O quadro de 4 categorias que o tópico 4 pede é exaustivo e mutuamente exclusivo por
    construção (vem direto de `destino`). Informalidade NÃO é uma quinta fatia da mesma pizza —
    uma pessoa pode mudar de grande grupo E se informalizar ao mesmo tempo — por isso ela entra
    como uma métrica condicional à parte (decisão documentada aqui, não silenciosa)."""
    def bloco(sub: pd.DataFrame) -> dict:
        obs = sub.loc[sub["destino"].notna()]
        tot = obs["peso"].sum()
        cat = {c: round(100 * obs.loc[obs["destino"] == c, "peso"].sum() / tot, 2) if tot else None
               for c in ["mesmo_grupo", "outro_grupo", "desocupado", "fora_da_forca"]}
        base_formal = sub.loc[sub["pareado"] & (sub["formal_origem"] == 1) & sub["condicao_destino"].notna()]
        informal = round(100 * base_formal.loc[base_formal["formal_para_informal"] == True, "peso"].sum() / base_formal["peso"].sum(), 2) if len(base_formal) else None
        return {"permaneceu_na_ocupacao": cat["mesmo_grupo"], "mudou_de_ocupacao": cat["outro_grupo"],
                "desemprego": cat["desocupado"], "fora_da_forca_de_trabalho": cat["fora_da_forca"],
                "informalidade_entre_quem_estava_formal": informal, "n": int(obs["n"].sum())}
    return {q: {"pre": bloco(p.loc[(p["periodo"] == "pre") & (p["quartil"] == q)]),
                "pos": bloco(p.loc[(p["periodo"] == "pos") & (p["quartil"] == q)])} for q in QUARTIS} | \
           {"Todos": {"pre": bloco(p.loc[p["periodo"] == "pre"]), "pos": bloco(p.loc[p["periodo"] == "pos"])}}


def did_variaveis() -> dict:
    """Reproduz a especificação já fixada em IDP/METODOLOGIA.md §5 e no README — não propõe nada
    novo. Serve só para deixar as variáveis nomeadas antes da estimação (tópico 7)."""
    return {
        "unidade_de_observacao": "Par pessoa-trimestre (entrevista de origem t ligada a t+1), "
            "agregado em células por UF × UPA × ocupação de origem × covariáveis.",
        "tratamento_exposicao": {"variavel": "aioe_origem", "tipo": "contínua, padronizada entre ocupações "
            "(desvio-padrão 0,9445 entre 416 códigos)", "interacao": "aioe_origem:pos"},
        "periodo": {"pre": f"destino até {ULTIMO_PRE}", "pos": f"origem a partir de {PRIMEIRO_POS}",
                     "excluido": f"{TRIMESTRE_PARCIAL} (parcialmente tratado) e {JANELA_ATIPICA[0]}–{JANELA_ATIPICA[1]} "
                                 "(coleta telefônica, sai só do pré)"},
        "outcomes_planejados": ["pareado (teste de atrito)", "muda_ocupacao_2", "muda_ocupacao_3",
            "sai_do_emprego", "formal_para_informal", "mobilidade_descendente_aioe", "mobilidade_ascendente_aioe"],
        "controles": ["telework:pos", "idade", "idade_quadrado", "sexo", "raça", "escolaridade",
            "tempo_emprego_categoria", "tamanho_empresa_categoria", "setor"],
        "efeitos_fixos": ["cod_origem (absorve o nível permanente de cada ocupação)",
            "sigla_uf × mês (absorve componentes aditivos comuns a cada UF-mês, inclusive o ciclo nacional)"],
        "pesos_e_cluster": {"pesos": "soma de V1028 da entrevista de origem (peso transversal)",
                              "cluster": "UPA — nível do desenho amostral"},
        "modelo": "LPM (pyfixest), não logit — com efeitos fixos de alta dimensão o LPM é o que "
                  "permite estimação e inferência viáveis; alvo é o efeito marginal médio.",
        "risco_de_identificacao": "Não é o viés clássico de adoção escalonada do TWFE (todo mundo é "
            "'tratado' na mesma data). O tratamento é contínuo (intensidade do AIOE), o que exige uma "
            "versão mais forte de tendências paralelas — Callaway, Goodman-Bacon & Sant'Anna (2024).",
        "proximos_passos": ["Diff-in-Diff com tratamento contínuo (LPM acima)",
            "Estudo de evento em torno de 2022T4", "Teste de tendências prévias (séries por quartil, Ato V)",
            "Robustez: sem a janela de coleta atípica, cluster alternativo, amostra restrita a pareados"],
    }


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    df = carregar()
    p, cortes = preparar(df)
    nomes = nomes_cod()

    resumo = quadro_resumo(df, p)
    desc = descritivas(p)
    matriz = matriz_transicao(p)
    top_o = top_ocupacoes(p, nomes, "origem")
    top_d = top_ocupacoes(p, nomes, "destino")
    ocup = ocupacoes_exposicao(p, nomes)
    dist = exposicao_distribuicao(p)
    serie = serie_emprego_quartil(p)
    quadro4 = o_que_aconteceu(p)
    didvars = did_variaveis()

    (SAIDA / "quadro_resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=1), encoding="utf-8")
    (SAIDA / "descritivas_geral.json").write_text(json.dumps(desc, ensure_ascii=False, indent=1), encoding="utf-8")
    (SAIDA / "o_que_aconteceu.json").write_text(json.dumps(quadro4, ensure_ascii=False, indent=1), encoding="utf-8")
    (SAIDA / "did_variaveis.json").write_text(json.dumps(didvars, ensure_ascii=False, indent=1), encoding="utf-8")
    matriz.to_csv(SAIDA / "matriz_transicao.csv", index=False, encoding="utf-8")
    top_o.to_csv(SAIDA / "top_ocupacoes_origem.csv", index=False, encoding="utf-8")
    top_d.to_csv(SAIDA / "top_ocupacoes_destino.csv", index=False, encoding="utf-8")
    ocup.to_csv(SAIDA / "ocupacoes_exposicao.csv", index=False, encoding="utf-8")
    dist.to_csv(SAIDA / "exposicao_distribuicao.csv", index=False, encoding="utf-8")
    serie.to_csv(SAIDA / "serie_emprego_quartil.csv", index=False, encoding="utf-8")

    dashboard = {
        "meta": {"gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"), "fonte": str(PAINEL),
                  "cortes_quartis_aioe_pre": cortes, "grandes_grupos": GRANDES_GRUPOS},
        "quadro_resumo": resumo, "descritivas": desc, "o_que_aconteceu": quadro4, "did_variaveis": didvars,
        "matriz_transicao": registros(matriz), "top_ocupacoes_origem": registros(top_o),
        "top_ocupacoes_destino": registros(top_d), "ocupacoes_exposicao": registros(ocup),
        "exposicao_distribuicao": registros(dist), "serie_emprego_quartil": registros(serie),
    }
    (SAIDA / "dashboard_data_v2.json").write_text(json.dumps(dashboard, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Saídas em {SAIDA}/")
    print(f"Ocupações no ranking de exposição (n>={MIN_N_OCUPACAO}): {ocup['cod'].nunique()}")


if __name__ == "__main__":
    main()
