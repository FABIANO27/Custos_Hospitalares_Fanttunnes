"""Dashboard de custos hospitalares por centro de custo.

Execução:
    pip install streamlit plotly pandas
    python gerar_base.py          # gera os CSVs (uma vez)
    streamlit run dashboard.py
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Custos Hospitalares", page_icon="🏥", layout="wide")

# ----------------------------------------------------------------------------
# Dados
# ----------------------------------------------------------------------------
@st.cache_data
def carregar():
    c = pd.read_csv("base_custos_hospitalares.csv", parse_dates=["competencia"])
    p = pd.read_csv("base_producao_receita.csv", parse_dates=["competencia"])
    return c, p


def brl(v: float, abrev: bool = True) -> str:
    """Formata valor em R$ (padrão brasileiro)."""
    if abrev and abs(v) >= 1e6:
        s = f"{v/1e6:,.2f} mi"
    elif abrev and abs(v) >= 1e3:
        s = f"{v/1e3:,.1f} mil"
    else:
        s = f"{v:,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(v: float) -> str:
    return f"{v:,.1f}%".replace(".", ",")


custos, prod = carregar()

# ----------------------------------------------------------------------------
# Filtros
# ----------------------------------------------------------------------------
st.sidebar.title("🏥 Filtros")
meses = sorted(custos["competencia"].unique())
ini, fim = st.sidebar.select_slider(
    "Período", options=meses, value=(meses[0], meses[-1]),
    format_func=lambda d: pd.Timestamp(d).strftime("%m/%Y"))
tipos = st.sidebar.multiselect("Tipo de centro", sorted(custos["tipo_centro"].unique()),
                               default=sorted(custos["tipo_centro"].unique()))
centros_disp = sorted(custos[custos["tipo_centro"].isin(tipos)]["centro_custo"].unique())
centros = st.sidebar.multiselect("Centro de custo", centros_disp, default=centros_disp)

mask_c = (custos["competencia"].between(ini, fim) & custos["tipo_centro"].isin(tipos)
          & custos["centro_custo"].isin(centros))
mask_p = (prod["competencia"].between(ini, fim) & prod["tipo_centro"].isin(tipos)
          & prod["centro_custo"].isin(centros))
c, p = custos[mask_c].copy(), prod[mask_p].copy()

if c.empty:
    st.warning("Nenhum dado para os filtros selecionados.")
    st.stop()

# ----------------------------------------------------------------------------
# Indicadores
# ----------------------------------------------------------------------------
realizado, orcado = c["realizado"].sum(), c["orcado"].sum()
variacao = realizado - orcado
variacao_pct = variacao / orcado * 100
receita = p["receita"].sum()
resultado = receita - realizado
margem = resultado / receita * 100 if receita else 0
pessoal_pct = c.loc[c["categoria_custo"] == "Pessoal", "realizado"].sum() / realizado * 100

pd_df = p[p["unidade_producao"] == "Paciente-dia"]
custo_pd = (c[c["centro_custo"].isin(pd_df["centro_custo"].unique())]["realizado"].sum()
            / pd_df["volume"].sum()) if pd_df["volume"].sum() else None
leitos = p[p["leitos_dia_disponiveis"] > 0]
ocupacao = (leitos["volume"].sum() / leitos["leitos_dia_disponiveis"].sum() * 100
            if not leitos.empty else None)

st.title("Painel Financeiro – Custos Hospitalares")
st.caption(f"Base fictícia • Competências {pd.Timestamp(ini):%m/%Y} a {pd.Timestamp(fim):%m/%Y}")

k = st.columns(6)
k[0].metric("Custo realizado", brl(realizado))
k[1].metric("Orçado", brl(orcado))
k[2].metric("Variação vs orçado", brl(variacao), pct(variacao_pct), delta_color="inverse")
k[3].metric("Receita", brl(receita))
k[4].metric("Resultado", brl(resultado), f"Margem {pct(margem)}")
k[5].metric("% Pessoal no custo", pct(pessoal_pct))

k2 = st.columns(4)
k2[0].metric("Custo por paciente-dia", brl(custo_pd, False) if custo_pd else "–")
k2[1].metric("Taxa de ocupação", pct(ocupacao) if ocupacao else "–")
k2[2].metric("Centros acima do orçado",
             f"{(c.groupby('centro_custo')[['realizado', 'orcado']].sum().eval('realizado > orcado')).sum()}"
             f" de {c['centro_custo'].nunique()}")
k2[3].metric("Custo médio mensal", brl(realizado / c["competencia"].nunique()))

st.divider()

# ----------------------------------------------------------------------------
# Abas
# ----------------------------------------------------------------------------
t1, t2, t3, t4 = st.tabs(["📈 Visão geral", "🏷️ Centros de custo", "🔥 Desvios", "📋 Dados"])

with t1:
    a, b = st.columns([3, 2])
    mensal = c.groupby("competencia")[["orcado", "realizado"]].sum().reset_index()
    rec_m = p.groupby("competencia")["receita"].sum().reset_index()
    mensal = mensal.merge(rec_m, on="competencia", how="left")
    fig = go.Figure()
    fig.add_bar(x=mensal["competencia"], y=mensal["realizado"], name="Realizado", marker_color="#1f77b4")
    fig.add_scatter(x=mensal["competencia"], y=mensal["orcado"], name="Orçado",
                    mode="lines+markers", line=dict(color="#ff7f0e", width=3))
    fig.add_scatter(x=mensal["competencia"], y=mensal["receita"], name="Receita",
                    mode="lines", line=dict(color="#2ca02c", dash="dot", width=3))
    fig.update_layout(title="Evolução mensal: custo realizado × orçado × receita",
                      height=400, legend=dict(orientation="h", y=-0.2), yaxis_tickformat=",.0f")
    a.plotly_chart(fig, use_container_width=True)

    comp = c.groupby("categoria_custo")["realizado"].sum().reset_index()
    fig = px.pie(comp, names="categoria_custo", values="realizado", hole=0.5,
                 title="Composição do custo por categoria")
    fig.update_layout(height=400, legend=dict(orientation="h", y=-0.2))
    b.plotly_chart(fig, use_container_width=True)

    mensal["resultado"] = mensal["receita"] - mensal["realizado"]
    fig = px.area(mensal, x="competencia", y="resultado", title="Resultado mensal (receita − custo)",
                  color_discrete_sequence=["#2ca02c"])
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(height=300)
    st.plotly_chart(fig, use_container_width=True)

with t2:
    por_centro = (c.groupby(["centro_custo", "tipo_centro"])[["orcado", "realizado"]].sum().reset_index()
                  .sort_values("realizado"))
    fig = px.bar(por_centro, x="realizado", y="centro_custo", color="tipo_centro", orientation="h",
                 title="Custo realizado por centro de custo", text_auto=".3s")
    fig.update_layout(height=520, yaxis_title=None, xaxis_title="R$")
    st.plotly_chart(fig, use_container_width=True)

    a, b = st.columns(2)
    cat_centro = c.groupby(["centro_custo", "categoria_custo"])["realizado"].sum().reset_index()
    fig = px.bar(cat_centro, x="centro_custo", y="realizado", color="categoria_custo",
                 title="Composição do custo por centro")
    fig.update_layout(height=450, xaxis_title=None, legend=dict(orientation="h", y=-0.5))
    a.plotly_chart(fig, use_container_width=True)

    res = (p.groupby("centro_custo")["receita"].sum().to_frame()
           .join(c.groupby("centro_custo")["realizado"].sum()).reset_index())
    res = res[res["receita"] > 0]
    res["resultado"] = res["receita"] - res["realizado"]
    res["margem_%"] = res["resultado"] / res["receita"] * 100
    res = res.sort_values("margem_%")
    fig = px.bar(res, x="margem_%", y="centro_custo", orientation="h",
                 color="margem_%", color_continuous_scale="RdYlGn", color_continuous_midpoint=0,
                 title="Margem direta por centro gerador de receita (sem rateio de apoio/administrativo)")
    fig.update_layout(height=450, yaxis_title=None, coloraxis_showscale=False)
    b.plotly_chart(fig, use_container_width=True)

    # Custo unitário por unidade de produção
    un = p[p["volume"] > 0].groupby(["centro_custo", "unidade_producao"])["volume"].sum().reset_index()
    un = un.merge(c.groupby("centro_custo")["realizado"].sum().reset_index(), on="centro_custo")
    un["custo_unitario"] = un["realizado"] / un["volume"]
    un["custo_unitario"] = un["custo_unitario"].map(lambda v: brl(v, False))
    un["volume"] = un["volume"].map(lambda v: f"{v:,.0f}".replace(",", "."))
    st.subheader("Custo unitário por centro")
    st.dataframe(un[["centro_custo", "unidade_producao", "volume", "custo_unitario"]]
                 .rename(columns={"centro_custo": "Centro", "unidade_producao": "Unidade",
                                  "volume": "Volume", "custo_unitario": "Custo unitário"}),
                 hide_index=True, use_container_width=True)

with t3:
    desv = c.groupby("centro_custo")[["orcado", "realizado"]].sum().reset_index()
    desv["var_rs"] = desv["realizado"] - desv["orcado"]
    desv["var_pct"] = desv["var_rs"] / desv["orcado"] * 100
    desv = desv.sort_values("var_pct")
    fig = px.bar(desv, x="var_pct", y="centro_custo", orientation="h", color="var_pct",
                 color_continuous_scale="RdYlGn_r", color_continuous_midpoint=0,
                 title="Variação % realizado × orçado (positivo = estouro)")
    fig.update_layout(height=520, yaxis_title=None, coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)

    heat = c.groupby(["centro_custo", "competencia"])[["orcado", "realizado"]].sum().reset_index()
    heat["var_pct"] = (heat["realizado"] / heat["orcado"] - 1) * 100
    heat["mes"] = heat["competencia"].dt.strftime("%m/%y")
    pivot = heat.pivot(index="centro_custo", columns="mes", values="var_pct")
    pivot = pivot[[m for m in heat.sort_values("competencia")["mes"].unique()]]
    fig = px.imshow(pivot, color_continuous_scale="RdYlGn_r", zmin=-15, zmax=15, aspect="auto",
                    title="Mapa de calor: variação % mensal por centro")
    fig.update_layout(height=550)
    st.plotly_chart(fig, use_container_width=True)

    top = (c.groupby(["centro_custo", "categoria_custo"])[["orcado", "realizado"]].sum().reset_index())
    top["var_rs"] = top["realizado"] - top["orcado"]
    st.subheader("Maiores estouros (centro × categoria)")
    top5 = top.sort_values("var_rs", ascending=False).head(10).copy()
    for col in ("orcado", "realizado", "var_rs"):
        top5[col] = top5[col].map(lambda v: brl(v, False))
    st.dataframe(top5.rename(columns={"centro_custo": "Centro", "categoria_custo": "Categoria",
                                      "orcado": "Orçado", "realizado": "Realizado", "var_rs": "Estouro"}),
                 hide_index=True, use_container_width=True)

with t4:
    st.dataframe(c.assign(competencia=c["competencia"].dt.strftime("%m/%Y")),
                 hide_index=True, use_container_width=True)
    st.download_button("⬇️ Baixar custos filtrados (CSV)",
                       c.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
                       "custos_filtrados.csv", "text/csv")
