# -*- coding: utf-8 -*-
"""
25_antecipacao_estrita.py - Antecipacao PURA: o modelo ve o DG chegando quando NADA esta iminente? (L12, CM 5.2)

Correcao de um furo nos scripts 23/24: o alvo "existe DG em [t+L, t+4h]" deixa
passar eventos em CASCATA (DG iminente em <L min E outro DG em [L, 4h]); nesses,
o modelo dispara pelo DG iminente, nao por antecipar o futuro. Isso inflava o
recall e a AUC-ROC.

Aqui o alvo e' ESTRITO ("antecipacao pura"):
  - lead(t) = tempo ate o PROXIMO DG (>= t) do equipamento.
  - positivo: L <= lead <= 4h   (proximo DG esta entre L e 4h; nada iminente antes de L)
  - negativo: lead > 4h ou sem DG (nada chegando em 4h)
  - EXCLUIDO: lead < L           (DG iminente/cascata — nao e' "antecipacao")

Se a AUC-ROC continuar alta nesse recorte estrito, a antecipacao e' genuina.
Se desabar, o "sucesso" de 90 min vinha de cascata e a L12 original (detector de
iminente) estava mais certa.

Compara, para cada L, o alvo INCLUSIVO (scripts 23/24) vs o ESTRITO.

Entradas: v3.parquet + lightgbm_v2_no_cascade.txt
Saidas:
  - Projeto/relatorio/tabelas/antecipacao_estrita.csv

Executar:
    PYTHONIOENCODING=utf-8 uv run python Projeto/codigo/25_antecipacao_estrita.py
"""
from pathlib import Path
import warnings

import lightgbm as lgb
import numpy as np
import polars as pl
from sklearn.metrics import average_precision_score, roc_auc_score, recall_score, precision_score

warnings.filterwarnings("ignore", category=UserWarning, module="lightgbm")

ROOT = Path(__file__).resolve().parents[1]
ARQ_V3 = ROOT / "dados" / "features" / "v3.parquet"
ARQ_MODELO = ROOT / "modelos" / "lightgbm_v2_no_cascade.txt"
ARQ_TAB = ROOT / "relatorio" / "tabelas" / "antecipacao_estrita.csv"

N_TEST = 71_089
LEADS_MIN = [30, 60, 90, 120]
THR_OP = 0.30

FEATURES = [
    "hora_dia", "dia_semana", "turno", "mes", "valor_disponivel",
    "count_critico_1h", "count_critico_2h", "count_critico_4h",
    "count_critico_8h", "count_critico_24h",
    "count_nao_critico_1h", "count_nao_critico_2h", "count_nao_critico_4h",
    "count_nao_critico_8h", "count_nao_critico_24h",
    "count_total_1h", "count_total_2h", "count_total_4h",
    "count_total_8h", "count_total_24h",
    "horas_desde_ultimo_critico",
    "estado_pre_evento",
    "razao_alarme_7d_vs_30d_anterior", "razao_severidade_14d_vs_60d",
    "taxa_DG_operador_30d", "n_bypasses_operador_7d",
    "qtd_alarmes_nivel_muito_alto_360min",
    "tag_freq", "frota_793D_2S", "frota_793D_3S",
    "frota_793D_4S", "frota_793D_5S", "tipo_caminhao", "operador_freq",
]
CAT_FEATURES = ["turno", "estado_pre_evento"]


def metr(t, p):
    n, npos = len(t), int(t.sum())
    prev = npos / n if n else 0.0
    auc_pr = float(average_precision_score(t, p)) if 0 < npos < n else None
    auc_roc = float(roc_auc_score(t, p)) if 0 < npos < n else None
    pred = (p >= THR_OP).astype(np.int8)
    rec = float(recall_score(t, pred, zero_division=0)) if npos else None
    prec = float(precision_score(t, pred, zero_division=0)) if npos else None
    lift = (auc_pr / prev) if (auc_pr and prev > 0) else None
    return {"n": n, "n_pos": npos, "prev": prev, "auc_pr": auc_pr,
            "auc_roc": auc_roc, "lift": lift, "recall_030": rec, "prec_030": prec}


def main():
    print("=" * 84)
    print("25_antecipacao_estrita.py - antecipacao PURA (sem contaminacao de cascata)")
    print("=" * 84)

    df = pl.read_parquet(ARQ_V3)
    test = df.filter(pl.col("split") == "test")
    assert test.height == N_TEST
    booster = lgb.Booster(model_file=str(ARQ_MODELO))
    X = test.select(FEATURES).to_pandas()
    for c in CAT_FEATURES:
        X[c] = X[c].astype("category")
    if X["valor_disponivel"].dtype == "bool":
        X["valor_disponivel"] = X["valor_disponivel"].astype(np.int8)
    p_all = booster.predict(X)

    base = test.select(["TAG", "Data_Evento"]).with_columns(pl.Series("p", p_all)).sort("Data_Evento")
    dgs = (test.filter(pl.col("Is_Dont_Go") == 1)
           .select(["TAG", pl.col("Data_Evento").alias("dg_time")]).sort("dg_time"))

    # lead = tempo ate o proximo DG (>= t)
    j = base.join_asof(dgs, left_on="Data_Evento", right_on="dg_time", by="TAG", strategy="forward")
    j = j.with_columns(
        pl.when(pl.col("dg_time").is_null())
        .then(None)
        .otherwise((pl.col("dg_time") - pl.col("Data_Evento")).dt.total_seconds() / 3600.0)
        .alias("lead_h")
    )
    lead = j["lead_h"].to_numpy()          # NaN = sem DG futuro
    p = j["p"].to_numpy()
    lead_filled = np.where(np.isnan(lead), np.inf, lead)

    linhas = []
    print(f"\n{'L(min)':>6} | {'alvo':<10} | {'n_aval':>7} | {'n_pos':>6} | {'prev':>6} | "
          f"{'AUC-PR':>7} | {'AUC-ROC':>7} | {'lift':>5} | {'rec@.30':>7} | {'prec@.30':>8}")
    print("-" * 96)
    for Lmin in LEADS_MIN:
        Lh = Lmin / 60.0

        # INCLUSIVO: existe DG em [t+L, t+4h] (permite iminente antes) -- aprox. script 23
        # (reconstruido aqui via lead: positivo se lead<=4h E (lead>=L OU existe DG depois);
        #  como so temos o proximo DG, aproximamos: inclusivo = lead <= 4h e lead-janela ...)
        # Para fidelidade, INCLUSIVO usa: positivo se ha QUALQUER DG em [t+L,t+4h].
        # Aproximacao com proximo DG subestima cascata; por isso medimos o ESTRITO como foco.
        incl_pos = (lead_filled <= 4.0) & (lead_filled >= 0.0)  # qualquer DG em (0,4h] ~ target_4h
        m_incl = metr(incl_pos.astype(np.int8), p)

        # ESTRITO: proximo DG em [L, 4h]; exclui iminente (lead < L)
        pos = (lead_filled >= Lh) & (lead_filled <= 4.0)
        neg = (lead_filled > 4.0)               # inclui inf (sem DG)
        keep = pos | neg
        m_str = metr(pos[keep].astype(np.int8), p[keep])

        linhas.append({"lead_min": Lmin, "alvo": "estrito", **m_str})
        for tag, m in [("incl(~4h)", m_incl), ("estrito", m_str)]:
            ap = f"{m['auc_pr']:.4f}" if m['auc_pr'] is not None else "N/A"
            ar = f"{m['auc_roc']:.4f}" if m['auc_roc'] is not None else "N/A"
            lf = f"{m['lift']:.2f}" if m['lift'] is not None else "N/A"
            rc = f"{m['recall_030']:.3f}" if m['recall_030'] is not None else "N/A"
            pr = f"{m['prec_030']:.3f}" if m['prec_030'] is not None else "N/A"
            print(f"{Lmin:>6} | {tag:<10} | {m['n']:>7,} | {m['n_pos']:>6,} | {m['prev']:>6.3f} | "
                  f"{ap:>7} | {ar:>7} | {lf:>5} | {rc:>7} | {pr:>8}")
        print("-" * 96)

    pl.from_dicts(linhas).write_csv(ARQ_TAB)
    print(f"Salvo: {ARQ_TAB.relative_to(ROOT.parent)}")

    print()
    print("=" * 84)
    print("LEITURA (alvo ESTRITO = antecipacao pura, sem iminente)")
    print("=" * 84)
    m90 = next(l for l in linhas if l["lead_min"] == 90)
    print(f"  Em L=90min estrito: n_pos={m90['n_pos']:,} (eventos com proximo DG entre 90min e 4h, nada antes)")
    print(f"    AUC-ROC={m90['auc_roc']:.4f} | lift={m90['lift']:.2f}x | recall@0.30={m90['recall_030']:.3f}")
    if m90['auc_roc'] is not None and m90['auc_roc'] >= 0.75:
        print("  -> AUC-ROC alta no estrito: antecipacao GENUINA (nao era so cascata).")
    elif m90['auc_roc'] is not None and m90['auc_roc'] >= 0.62:
        print("  -> AUC-ROC moderada: antecipacao parcial e real, porem mais fraca que o inclusivo sugeria.")
    else:
        print("  -> AUC-ROC baixa: o 'sucesso' de 90min vinha de cascata; L12 original estava mais certa.")
    print("=" * 84)


if __name__ == "__main__":
    main()
