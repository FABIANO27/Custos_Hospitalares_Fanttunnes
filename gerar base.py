"""Gera base FICTÍCIA de custos hospitalares por centro de custo.

Saídas:
  base_custos_hospitalares.csv  -> custos mensais (orçado x realizado) por centro e categoria
  base_producao_receita.csv     -> volume de produção e receita mensal por centro
"""
import numpy as np
import pandas as pd

rng = np.random.default_rng(42)

# (código, nome, tipo, unidade de produção, custo mensal base R$, receita por unidade R$, volume mensal base)
CENTROS = [
    ("1001", "UTI Adulto",            "Assistencial",   "Paciente-dia", 2_400_000, 3_800, 520),
    ("1002", "UTI Neonatal",          "Assistencial",   "Paciente-dia", 1_500_000, 3_300, 330),
    ("1003", "Centro Cirúrgico",      "Assistencial",   "Cirurgia",     3_100_000, 9_500, 620),
    ("1004", "Pronto-Socorro",        "Assistencial",   "Atendimento",  1_900_000,   620, 5_800),
    ("1005", "Internação Clínica",    "Assistencial",   "Paciente-dia", 2_000_000, 1_250, 2_300),
    ("1006", "Maternidade",           "Assistencial",   "Parto",        1_200_000, 5_200, 290),
    ("1007", "Hemodinâmica",          "Assistencial",   "Procedimento", 1_100_000, 6_800, 240),
    ("2001", "Laboratório",           "Apoio",          "Exame",          900_000,    42, 38_000),
    ("2002", "Diagnóstico por Imagem","Apoio",          "Exame",        1_300_000,   310, 6_200),
    ("2003", "Farmácia",              "Apoio",          "Dispensação",    700_000,     0, 21_000),
    ("2004", "Nutrição e Dietética",  "Apoio",          "Refeição",       650_000,     0, 52_000),
    ("2005", "Lavanderia",            "Apoio",          "Kg roupa",       350_000,     0, 68_000),
    ("3001", "Administração Geral",   "Administrativo", "-",            1_000_000,     0, 0),
    ("3002", "TI",                    "Administrativo", "-",              480_000,     0, 0),
    ("3003", "Manutenção Predial",    "Administrativo", "-",              520_000,     0, 0),
]

# Perfil de composição do custo por tipo (pessoal, materiais/medicamentos, terceiros, manutenção, utilidades, outros)
CATEGORIAS = ["Pessoal", "Materiais e Medicamentos", "Serviços Terceirizados",
              "Manutenção", "Utilidades", "Outras Despesas"]
PERFIL = {
    "Assistencial":   [0.52, 0.30, 0.08, 0.04, 0.03, 0.03],
    "Apoio":          [0.40, 0.30, 0.15, 0.06, 0.05, 0.04],
    "Administrativo": [0.50, 0.05, 0.25, 0.08, 0.06, 0.06],
}
# Centros com perfis específicos
PERFIL_ESP = {
    "1003": [0.38, 0.45, 0.07, 0.04, 0.03, 0.03],  # Centro cirúrgico: OPME pesa mais
    "2003": [0.30, 0.55, 0.05, 0.03, 0.03, 0.04],  # Farmácia
    "2004": [0.35, 0.45, 0.08, 0.04, 0.05, 0.03],  # Nutrição
    "2002": [0.35, 0.20, 0.15, 0.20, 0.05, 0.05],  # Imagem: manutenção de equipamentos
}

competencias = pd.period_range("2025-01", "2026-10", freq="M")

custos, producao = [], []

for i, comp in enumerate(competencias):
    mes = comp.month
    # sazonalidade: pico respiratório (mai-ago) e leve queda em dez/jan
    sazon = 1 + 0.07 * np.sin((mes - 3) / 12 * 2 * np.pi) + (0.04 if mes in (5, 6, 7) else 0)
    # inflação setorial ~0,7% a.m.
    infl = 1.007 ** i
    # dissídio / reajuste de pessoal em maio
    reaj_pessoal = 1.055 if comp >= pd.Period("2025-05", "M") else 1.0
    if comp >= pd.Period("2026-05", "M"):
        reaj_pessoal *= 1.05

    for cod, nome, tipo, unid, base, rec_un, vol_base in CENTROS:
        perfil = PERFIL_ESP.get(cod, PERFIL[tipo])
        fator_vol = sazon * rng.normal(1, 0.03)
        for cat, pct in zip(CATEGORIAS, perfil):
            orcado = base * pct * infl * (reaj_pessoal if cat == "Pessoal" else 1) * 0.97
            # custo variável acompanha volume; fixo oscila pouco
            variavel = cat in ("Materiais e Medicamentos", "Serviços Terceirizados")
            fator = fator_vol if variavel else rng.normal(1, 0.015)
            desvio = rng.normal(1.03, 0.04)  # tendência de estouro de ~3%
            # alguns "problemas" intencionais para o dashboard ter o que mostrar
            if cod == "1001" and cat == "Materiais e Medicamentos" and comp >= pd.Period("2026-03", "M"):
                desvio += 0.12
            if cod == "1003" and cat == "Pessoal" and comp >= pd.Period("2026-06", "M"):
                desvio += 0.08   # horas extras
            if cod == "3002" and cat == "Serviços Terceirizados":
                desvio -= 0.06
            realizado = orcado * fator * desvio
            custos.append({
                "competencia": comp.to_timestamp().date(),
                "codigo_centro": cod, "centro_custo": nome, "tipo_centro": tipo,
                "categoria_custo": cat,
                "orcado": round(orcado, 2), "realizado": round(realizado, 2),
            })

        volume = int(round(vol_base * fator_vol)) if vol_base else 0
        receita = round(volume * rec_un * infl * rng.normal(1, 0.02), 2) if rec_un else 0.0
        producao.append({
            "competencia": comp.to_timestamp().date(),
            "codigo_centro": cod, "centro_custo": nome, "tipo_centro": tipo,
            "unidade_producao": unid, "volume": volume, "receita": receita,
            # leitos-dia disponíveis (para taxa de ocupação, só centros de internação)
            "leitos_dia_disponiveis": {"1001": 30, "1002": 20, "1005": 90}.get(cod, 0) * comp.days_in_month,
        })

pd.DataFrame(custos).to_csv("base_custos_hospitalares.csv", index=False, encoding="utf-8-sig")
pd.DataFrame(producao).to_csv("base_producao_receita.csv", index=False, encoding="utf-8-sig")
print(f"Custos: {len(custos)} linhas | Produção: {len(producao)} linhas")
