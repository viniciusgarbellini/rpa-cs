"""Dashboard Streamlit — evidência visual das automações em execução.

Exibe:
  • Estado atual dos ativos (cadastro + última leitura por motor)
  • Histórico de execuções dos bots (auditoria RPA)
  • Gráfico de séries temporais por motor
  • Resumo da qualidade dos dados (quality_score por fonte)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permite import de src.* mesmo rodando dentro do container do dashboard
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.express as px
import streamlit as st

from src.db.repository import Repository

st.set_page_config(page_title="RPA CS — Monitor de Ativos", layout="wide")

# Auto-refresh a cada 15s pra demo dinâmica
st.markdown(
    """
    <meta http-equiv="refresh" content="15">
    """,
    unsafe_allow_html=True,
)

st.title("🤖 RPA CS — Monitor de Ativos Industriais")
st.caption("Coleta automatizada · Normalização · Persistência · Auditoria")

repo = Repository()

# ---------- TOPO: cards de ativos -------------------------------------------

st.subheader("Ativos cadastrados (última leitura)")

assets = repo.list_assets_with_last_reading()
if not assets:
    st.warning("Nenhum ativo encontrado. O orquestrador já rodou pelo menos uma vez?")
else:
    cols = st.columns(min(len(assets), 4))
    for i, a in enumerate(assets):
        c = cols[i % len(cols)]
        last_t = a.get("last_temperature_c")
        last_v = a.get("last_vibration_mm_s")
        last_p = a.get("last_power_kw")
        last_at = a.get("last_reading_at")

        status_emoji = {"ACTIVE": "🟢", "MAINTENANCE": "🟡", "INACTIVE": "🔴"}.get(
            a.get("status", ""), "⚪"
        )
        with c:
            st.metric(
                label=f"{status_emoji} {a['tag']} — {a['name'][:30]}",
                value=f"{last_p:.1f} kW" if last_p else "—",
                delta=f"{last_t:.1f}°C / {last_v:.2f} mm/s" if last_t else None,
            )
            st.caption(f"Última: {last_at}" if last_at else "Sem leituras ainda")

st.divider()

# ---------- MEIO: gráficos por ativo ----------------------------------------

st.subheader("Séries temporais (últimas 24h)")

if assets:
    tag_options = [a["tag"] for a in assets]
    selected_tag = st.selectbox("Selecione um ativo", tag_options, index=0)
    history = repo.readings_history(selected_tag, hours=24)

    if not history:
        st.info("Sem leituras nas últimas 24h pra esse ativo.")
    else:
        df = pd.DataFrame(history)
        df["measured_at"] = pd.to_datetime(df["measured_at"])

        col_a, col_b = st.columns(2)
        with col_a:
            fig = px.line(df, x="measured_at", y="temperature_c",
                          title="Temperatura (°C)", markers=True)
            st.plotly_chart(fig, use_container_width=True)

            fig = px.line(df, x="measured_at", y="vibration_mm_s",
                          title="Vibração (mm/s)", markers=True)
            st.plotly_chart(fig, use_container_width=True)
        with col_b:
            fig = px.line(df, x="measured_at", y="power_kw",
                          title="Potência ativa (kW)", markers=True)
            st.plotly_chart(fig, use_container_width=True)

            fig = px.line(df, x="measured_at", y="quality_score",
                          title="Qualidade dos dados (0..1)", markers=True,
                          range_y=[0, 1.05])
            st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---------- BASE: auditoria de execuções RPA --------------------------------

st.subheader("Auditoria RPA — execuções recentes")

execs = repo.recent_executions(limit=30)
if not execs:
    st.info("Nenhuma execução registrada ainda.")
else:
    df_exec = pd.DataFrame(execs)
    st.dataframe(
        df_exec,
        use_container_width=True,
        hide_index=True,
        column_config={
            "started_at": st.column_config.DatetimeColumn("Início"),
            "finished_at": st.column_config.DatetimeColumn("Fim"),
            "duration_ms": st.column_config.NumberColumn("Duração (ms)"),
            "status": st.column_config.TextColumn("Status"),
        },
    )

st.caption(
    "🔄 Página recarrega automaticamente a cada 15s · "
    "Logs estruturados em ./logs/rpa.log · "
    "Schema completo em src/db/schema.sql"
)
