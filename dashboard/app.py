from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import datetime
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.connection import get_database, get_mongo_client, get_mongo_uri
from database.operations import get_collection_stats, get_financial_series, get_market_history
from src.data_pipeline import (
    customer_summary,
    load_capital_risk_history,
    load_customer_sample,
    load_financial_history,
)

st.set_page_config(
    page_title="Nubank 2.0 | Dashboard Inteligente & Mercado",
    page_icon="💜",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Paleta Nubank
NU_PURPLE = "#820AD1"
NU_DARK = "#2F0549"
NU_MID = "#6B16A8"
NU_LIGHT = "#F7F2FA"
TEXT = "#17131A"
MUTED = "#6F6673"
GRID = "#ECE7EF"
POSITIVE = "#157A54"
NEGATIVE = "#B42318"

st.markdown(
    f"""
    <style>
        .stApp {{ background: #FCFBFD; color: {TEXT}; }}
        .block-container {{ max-width: 1320px; padding-top: 1.5rem; padding-bottom: 3.5rem; }}
        [data-testid="stSidebar"] {{ background: #F6F2F8; border-right: 1px solid #E8DFEC; }}
        h1, h2, h3 {{ letter-spacing: -0.03em; color: {TEXT}; }}
        .hero {{
            background: linear-gradient(118deg, #250038 0%, {NU_DARK} 46%, {NU_PURPLE} 100%);
            border-radius: 22px;
            padding: 2rem 2.4rem;
            color: white;
            margin-bottom: 1.2rem;
            box-shadow: 0 16px 45px rgba(47, 5, 73, .14);
        }}
        .hero .kicker {{ font-size: .78rem; font-weight: 700; letter-spacing: .15em; text-transform: uppercase; opacity: .8; }}
        .hero h1 {{ color: white; font-size: 2.4rem; margin: .3rem 0 .5rem 0; line-height: 1.1; }}
        .hero p {{ color: rgba(255,255,255,.85); font-size: 1.02rem; max-width: 900px; margin: 0; line-height: 1.5; }}
        .metric-card {{
            background: white; border: 1px solid #E9E1ED; border-radius: 16px;
            padding: 1.1rem 1.2rem; min-height: 120px;
            box-shadow: 0 6px 20px rgba(31, 12, 39, .04);
        }}
        .metric-label {{ color: {MUTED}; font-size: .75rem; letter-spacing: .06em; text-transform: uppercase; font-weight: 700; }}
        .metric-value {{ color: {NU_DARK}; font-size: 1.8rem; font-weight: 800; margin: .2rem 0 .1rem; }}
        .metric-note {{ color: {MUTED}; font-size: .8rem; }}
        .status-badge {{
            display: inline-block; padding: .3rem .75rem; border-radius: 999px;
            font-size: .78rem; font-weight: 700; margin-bottom: 1rem;
        }}
        .status-online {{ background: #E6F7ED; color: #127A45; border: 1px solid #B8E8CA; }}
        .status-offline {{ background: #FDE8E8; color: #9B1C1C; border: 1px solid #F8B4B4; }}
        /* Abas: contraste garantido em qualquer tema do sistema */
        .stTabs [role="tablist"] {{ gap: .4rem; border-bottom: 1px solid #E8DFEC; padding-bottom: .5rem; flex-wrap: wrap; }}
        .stTabs [role="tab"] {{
            background: #FFFFFF; border: 1px solid #DCCFE3; border-radius: 999px;
            padding: .45rem 1rem; height: auto; color: {TEXT} !important;
        }}
        .stTabs [role="tab"] p {{ color: inherit !important; font-weight: 700; font-size: .9rem; }}
        .stTabs [role="tab"]:hover {{ border-color: {NU_PURPLE}; color: {NU_PURPLE} !important; }}
        .stTabs [role="tab"][aria-selected="true"] {{ background: {NU_PURPLE}; border-color: {NU_PURPLE}; color: #FFFFFF !important; }}
        .stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display: none; }}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_market_data() -> tuple[pd.DataFrame, bool, str]:
    """Carrega dados da coleção historico_diario do MongoDB Atlas."""
    uri = get_mongo_uri()
    if not uri:
        return _fallback_market_data(), False, "MONGO_URI não configurada (usando dados de demonstração)"

    client = None
    try:
        client = get_mongo_client(uri, timeout_ms=4000)
        db = get_database(client)
        col = db["historico_diario"]
        records = list(col.find({}, {"_id": 0}).sort("datetime", 1))
        if not records:
            return _fallback_market_data(), False, "Nenhum registro em nubank_db.historico_diario"
        df = pd.DataFrame(records)
        df["datetime"] = pd.to_datetime(df["datetime"])
        return df, True, f"MongoDB Atlas conectado · {len(df)} cotações sincronizadas"
    except Exception as e:
        return _fallback_market_data(), False, f"Falha de conexão com MongoDB Atlas: {type(e).__name__}"
    finally:
        if client:
            client.close()


def _fallback_market_data() -> pd.DataFrame:
    """Gera série histórica demonstrativa caso o banco ainda não tenha sido populado."""
    dates = pd.date_range(end=pd.Timestamp.now(), periods=30, freq="B")
    dfs = []
    base_prices = {"NU": 13.50, "ITUB": 6.80, "BBD": 2.50}
    for ticker, base in base_prices.items():
        sub = pd.DataFrame({
            "ticker": ticker,
            "datetime": dates,
            "open": [round(base * (1 + (i % 7 - 3) * 0.012), 2) for i in range(len(dates))],
            "high": [round(base * (1 + (i % 7 - 1) * 0.018), 2) for i in range(len(dates))],
            "low": [round(base * (1 + (i % 7 - 4) * 0.015), 2) for i in range(len(dates))],
            "close": [round(base * (1 + (i % 7 - 2) * 0.013), 2) for i in range(len(dates))],
            "volume": [1_200_000 + (i * 25_000) for i in range(len(dates))],
            "source": "Twelve Data (demonstração local)",
        })
        dfs.append(sub)
    return pd.concat(dfs, ignore_index=True)


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_fundamental_data():
    financial = load_financial_history()
    risk, risk_source = load_capital_risk_history()
    complaints, complaints_source = load_customer_sample()
    return financial, risk, risk_source, complaints, complaints_source


# Barra lateral de controle
st.sidebar.markdown("### ⚙️ Painel de Controle")
if st.sidebar.button("🔄 Sincronizar com MongoDB Atlas"):
    st.cache_data.clear()
    st.rerun()

market_df, is_connected, status_msg = fetch_market_data()
financial, risk, risk_source, complaints, complaints_source = fetch_fundamental_data()

# Status de Conexão
if is_connected:
    st.sidebar.markdown(f"<span class='status-badge status-online'>● {status_msg}</span>", unsafe_allow_html=True)
else:
    st.sidebar.markdown(f"<span class='status-badge status-offline'>○ {status_msg}</span>", unsafe_allow_html=True)

st.sidebar.markdown("---")
st.sidebar.markdown("### 📈 Filtro de Mercado (Twelve Data)")
available_tickers = sorted(market_df["ticker"].unique().tolist())
selected_ticker = st.sidebar.selectbox(
    "Selecione o ativo",
    available_tickers,
    index=available_tickers.index("NU") if "NU" in available_tickers else 0,
)

min_date = market_df["datetime"].min().date()
max_date = market_df["datetime"].max().date()
date_range = st.sidebar.date_input("Período de cotações", [min_date, max_date])

# Hero Header
st.markdown(
    """
    <div class="hero">
      <div class="kicker">Projeto Integrador · Fatec Sebrae · Big Data & NoSQL</div>
      <h1>Nubank 2.0 · Dashboard Analítico & Cotações</h1>
      <p>Monitoramento contínuo das ações da Nu Holdings (NYSE: NU) integrado diretamente à API Twelve Data e MongoDB Atlas, com análise de fundamentos contábeis e prudenciais.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_market, tab_overview, tab_profit, tab_risk, tab_architecture = st.tabs([
    "📈 Mercado & Ações (API Twelve)",
    "📊 Visão Geral de Crescimento",
    "💰 Rentabilidade e Eficiência",
    "🛡️ Capital e Risco (Pilar 3)",
    "🏗️ Arquitetura & MongoDB Atlas",
])

# ==========================================
# ABA 1: MERCADO & AÇÕES (API TWELVE DATA)
# ==========================================
with tab_market:
    st.markdown("## Cotações Diárias & Performance de Mercado")
    st.markdown(
        f"<div style='color:{MUTED}; margin-bottom:1rem;'>"
        f"Dados coletados automaticamente da <b>API Twelve Data</b> e persistidos no <b>MongoDB Atlas</b>. "
        f"Sem necessidade de manipulação manual de arquivos planilhados.</div>",
        unsafe_allow_html=True,
    )

    # Filtragem dos dados
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start_d, end_d = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
        df_filtered = market_df[
            (market_df["ticker"] == selected_ticker) &
            (market_df["datetime"] >= start_d) &
            (market_df["datetime"] <= end_d)
        ].sort_values("datetime").copy()
    else:
        df_filtered = market_df[market_df["ticker"] == selected_ticker].sort_values("datetime").copy()

    if df_filtered.empty:
        st.warning(f"Nenhum registro encontrado para '{selected_ticker}' no intervalo selecionado.")
    else:
        # Médias móveis
        df_filtered["sma_7"] = df_filtered["close"].rolling(7, min_periods=1).mean()
        df_filtered["sma_21"] = df_filtered["close"].rolling(21, min_periods=1).mean()

        latest_record = df_filtered.iloc[-1]
        first_record = df_filtered.iloc[0]
        var_pct = ((latest_record["close"] / first_record["close"]) - 1) * 100
        vol_mean = df_filtered["volume"].mean()

        # Cards com métricas principais
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(f"""
            <div class='metric-card'>
                <div class='metric-label'>Último Fechamento ({selected_ticker})</div>
                <div class='metric-value'>US$ {latest_record['close']:.2f}</div>
                <div class='metric-note'>Pregão de {latest_record['datetime'].strftime('%d/%m/%Y')}</div>
            </div>
        """, unsafe_allow_html=True)

        c2.markdown(f"""
            <div class='metric-card'>
                <div class='metric-label'>Variação no Período</div>
                <div class='metric-value' style='color: {POSITIVE if var_pct >= 0 else NEGATIVE};'>
                    {var_pct:+.2f}%
                </div>
                <div class='metric-note'>Comparado a {first_record['datetime'].strftime('%d/%m/%Y')}</div>
            </div>
        """, unsafe_allow_html=True)

        c3.markdown(f"""
            <div class='metric-card'>
                <div class='metric-label'>Faixa no Período (Mín / Máx)</div>
                <div class='metric-value'>US$ {df_filtered['low'].min():.2f} - {df_filtered['high'].max():.2f}</div>
                <div class='metric-note'>Amplitude: US$ {df_filtered['high'].max() - df_filtered['low'].min():.2f}</div>
            </div>
        """, unsafe_allow_html=True)

        c4.markdown(f"""
            <div class='metric-card'>
                <div class='metric-label'>Volume Médio Diário</div>
                <div class='metric-value'>{vol_mean / 1e6:.2f}M</div>
                <div class='metric-note'>Ações negociadas por dia</div>
            </div>
        """, unsafe_allow_html=True)

        # Gráfico Candlestick + Volume + SMA
        st.markdown(f"### Histórico OHLC & Médias Móveis · {selected_ticker}")
        fig_candle = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.06,
            row_heights=[0.75, 0.25],
        )

        fig_candle.add_trace(
            go.Candlestick(
                x=df_filtered["datetime"],
                open=df_filtered["open"],
                high=df_filtered["high"],
                low=df_filtered["low"],
                close=df_filtered["close"],
                name="OHLC",
                increasing_line_color=POSITIVE,
                decreasing_line_color=NEGATIVE,
            ),
            row=1, col=1,
        )

        fig_candle.add_trace(
            go.Scatter(
                x=df_filtered["datetime"],
                y=df_filtered["sma_7"],
                name="Média Móvel (7d)",
                line=dict(color=NU_PURPLE, width=2),
            ),
            row=1, col=1,
        )

        fig_candle.add_trace(
            go.Scatter(
                x=df_filtered["datetime"],
                y=df_filtered["sma_21"],
                name="Média Móvel (21d)",
                line=dict(color="#FF8C00", width=2, dash="dot"),
            ),
            row=1, col=1,
        )

        colors_vol = [
            POSITIVE if c >= o else NEGATIVE
            for c, o in zip(df_filtered["close"], df_filtered["open"])
        ]
        fig_candle.add_trace(
            go.Bar(
                x=df_filtered["datetime"],
                y=df_filtered["volume"],
                name="Volume",
                marker_color=colors_vol,
                opacity=0.6,
            ),
            row=2, col=1,
        )

        fig_candle.update_layout(
            template="plotly_white",
            height=540,
            margin=dict(l=20, r=20, t=30, b=20),
            xaxis_rangeslider_visible=False,
            legend=dict(orientation="h", y=1.05, x=0),
        )
        fig_candle.update_yaxes(title_text="Preço (US$)", gridcolor=GRID, row=1, col=1)
        fig_candle.update_yaxes(title_text="Volume", gridcolor=GRID, row=2, col=1)
        st.plotly_chart(fig_candle, use_container_width=True)

        # Comparativo de Performance Relativa (Normalizado)
        st.markdown("### Comparativo de Performance Relativa (Base 100)")
        comp_df = market_df.copy()
        pivoted = comp_df.pivot(index="datetime", columns="ticker", values="close").dropna()
        if not pivoted.empty and len(pivoted.columns) > 1:
            norm_df = (pivoted / pivoted.iloc[0]) * 100
            fig_comp = go.Figure()
            color_map = {"NU": NU_PURPLE, "ITUB": "#E26B00", "BBD": "#CC092F"}
            dash_map = {"NU": "solid", "ITUB": "dash", "BBD": "dot"}
            for col in norm_df.columns:
                fig_comp.add_trace(go.Scatter(
                    x=norm_df.index,
                    y=norm_df[col],
                    mode="lines+markers",
                    name=col,
                    line=dict(color=color_map.get(col, "#555"), width=3 if col == "NU" else 2, dash=dash_map.get(col, "solid")),
                    marker=dict(size=6),
                ))
            fig_comp.add_hline(y=100, line_dash="dash", line_color="#888")
            fig_comp.update_layout(
                template="plotly_white",
                height=400,
                margin=dict(l=20, r=20, t=30, b=20),
                yaxis_title="Retorno Normalizado (Base 100 = 1º pregão)",
                legend=dict(orientation="h", y=1.08, x=0),
            )
            fig_comp.update_yaxes(gridcolor=GRID)
            st.plotly_chart(fig_comp, use_container_width=True)

# ==========================================
# ABA 2: VISÃO GERAL DE CRESCIMENTO
# ==========================================
with tab_overview:
    st.markdown("## Crescimento que se converteu em monetização")
    fin = financial.copy()
    latest_fin = fin.iloc[-1]
    first_fin = fin.iloc[0]

    cols = st.columns(4)
    cols[0].markdown(f"""
        <div class='metric-card'>
            <div class='metric-label'>Clientes Ativos</div>
            <div class='metric-value'>{latest_fin.customers_m:.1f} mi</div>
            <div class='metric-note'>+{((latest_fin.customers_m / first_fin.customers_m) - 1) * 100:.0f}% desde 2021</div>
        </div>
    """, unsafe_allow_html=True)
    cols[1].markdown(f"""
        <div class='metric-card'>
            <div class='metric-label'>Receita Anual</div>
            <div class='metric-value'>US$ {latest_fin.revenue_usd_b:.2f} bi</div>
            <div class='metric-note'>{latest_fin.revenue_usd_b / first_fin.revenue_usd_b:.1f}× o nível de 2021</div>
        </div>
    """, unsafe_allow_html=True)
    cols[2].markdown(f"""
        <div class='metric-card'>
            <div class='metric-label'>Lucro Líquido</div>
            <div class='metric-value'>US$ {latest_fin.net_income_usd_b:.2f} bi</div>
            <div class='metric-note'>IFRS · reportado</div>
        </div>
    """, unsafe_allow_html=True)
    cols[3].markdown(f"""
        <div class='metric-card'>
            <div class='metric-label'>Depósitos</div>
            <div class='metric-value'>US$ {latest_fin.deposits_usd_b:.1f} bi</div>
            <div class='metric-note'>{latest_fin.deposits_usd_b / first_fin.deposits_usd_b:.1f}× desde 2021</div>
        </div>
    """, unsafe_allow_html=True)

    left, right = st.columns(2)
    with left:
        fig_rev = go.Figure()
        fig_rev.add_trace(go.Bar(x=fin.year, y=fin.revenue_usd_b, name="Receita", marker_color=NU_PURPLE))
        fig_rev.add_trace(go.Scatter(x=fin.year, y=fin.net_income_usd_b, name="Lucro líquido", mode="lines+markers", line=dict(color=NU_DARK, width=3), marker=dict(size=8)))
        fig_rev.add_hline(y=0, line_width=1, line_color="#999")
        fig_rev.update_layout(title="Receita e Lucro Líquido Anual (US$ bi)", template="plotly_white", height=380, legend=dict(orientation="h", y=1.08, x=0))
        st.plotly_chart(fig_rev, use_container_width=True)

    with right:
        fig_arpac = go.Figure()
        fig_arpac.add_trace(go.Scatter(x=fin.year, y=fin.arpac_usd, name="ARPAC mensal", mode="lines+markers", line=dict(color=NU_PURPLE, width=4), marker=dict(size=8)))
        fig_arpac.add_trace(go.Scatter(x=fin.year, y=fin.cost_to_serve_usd, name="Custo de servir", mode="lines+markers", line=dict(color="#777", width=2.5, dash="dot"), marker=dict(size=7)))
        fig_arpac.update_layout(title="Monetização (ARPAC) vs Custo de Servir (US$)", template="plotly_white", height=380, legend=dict(orientation="h", y=1.08, x=0))
        st.plotly_chart(fig_arpac, use_container_width=True)

# ==========================================
# ABA 3: RENTABILIDADE E EFICIÊNCIA
# ==========================================
with tab_profit:
    st.markdown("## Evolução das Margens & Inflexão de Lucro")
    prof = financial.copy()
    prof["gross_margin"] = (prof["gross_profit_usd_b"] / prof["revenue_usd_b"]) * 100
    prof["net_margin"] = (prof["net_income_usd_b"] / prof["revenue_usd_b"]) * 100

    left, right = st.columns(2)
    with left:
        colors_inc = [NEGATIVE if val < 0 else POSITIVE for val in prof["net_income_usd_b"]]
        fig_inc = go.Figure()
        fig_inc.add_trace(go.Bar(x=prof.year, y=prof.net_income_usd_b, marker_color=colors_inc, text=[f"US$ {v:.2f} bi" for v in prof.net_income_usd_b], textposition="outside"))
        fig_inc.add_hline(y=0, line_width=1, line_color="#999")
        fig_inc.update_layout(title="Lucro Líquido Contábil (IFRS)", yaxis_title="US$ bilhões", template="plotly_white", height=400)
        st.plotly_chart(fig_inc, use_container_width=True)

    with right:
        fig_m = go.Figure()
        fig_m.add_trace(go.Scatter(x=prof.year, y=prof.gross_margin, name="Margem Bruta", mode="lines+markers", line=dict(color=NU_PURPLE, width=4)))
        fig_m.add_trace(go.Scatter(x=prof.year, y=prof.net_margin, name="Margem Líquida", mode="lines+markers", line=dict(color=NU_DARK, width=3)))
        fig_m.add_hline(y=0, line_width=1, line_color="#999")
        fig_m.update_layout(title="Margens Implícitas (% da Receita)", yaxis_title="%", template="plotly_white", height=400, legend=dict(orientation="h", y=1.08, x=0))
        st.plotly_chart(fig_m, use_container_width=True)

# ==========================================
# ABA 4: CAPITAL E RISCO (PILAR 3)
# ==========================================
with tab_risk:
    st.markdown("## Absorção de Risco & Índices Prudenciais")
    st.caption(f"Fonte: {risk_source}")
    risk_df = risk.copy()
    if not risk_df.empty:
        left, right = st.columns(2)
        with left:
            fig_cap = go.Figure()
            if "capital_principal_brl_b" in risk_df.columns:
                fig_cap.add_trace(go.Scatter(x=risk_df.period, y=risk_df.capital_principal_brl_b, mode="lines+markers", name="Capital Principal", line=dict(color=NU_PURPLE, width=4)))
            if "rwa_total_brl_b" in risk_df.columns:
                fig_cap.add_trace(go.Scatter(x=risk_df.period, y=risk_df.rwa_total_brl_b, mode="lines+markers", name="RWA Total", line=dict(color=NU_DARK, width=3)))
            fig_cap.update_layout(title="Capital Principal e RWA (R$ bilhões)", template="plotly_white", height=400, legend=dict(orientation="h", y=1.08, x=0))
            st.plotly_chart(fig_cap, use_container_width=True)

        with right:
            fig_ind = go.Figure()
            if "basel_index_pct" in risk_df.columns:
                fig_ind.add_trace(go.Scatter(x=risk_df.period, y=risk_df.basel_index_pct, mode="lines+markers", name="Índice de Basileia", line=dict(color=NU_PURPLE, width=4)))
            if "icp_pct" in risk_df.columns:
                fig_ind.add_trace(go.Scatter(x=risk_df.period, y=risk_df.icp_pct, mode="lines+markers", name="ICP", line=dict(color="#A26AC5", width=3, dash="dot")))
            fig_ind.update_layout(title="Índices de Basileia e Capital Principal (%)", template="plotly_white", height=400, legend=dict(orientation="h", y=1.08, x=0))
            st.plotly_chart(fig_ind, use_container_width=True)

# ==========================================
# ABA 5: ARQUITETURA & MONGODB ATLAS
# ==========================================
with tab_architecture:
    st.markdown("## Arquitetura Automatizada Nubank 2.0")
    st.markdown(
        """
        Esta versão substituiu a dependência de arquivos planilhados manuais por um fluxo moderno de **Big Data e NoSQL**:
        """
    )
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### 🔄 Fluxo de Ingestão Contínua")
        st.code(
            """API Twelve Data (Cotações OHLCV)
       │
       ▼
Validação de Dados (Schema & Range Check)
       │
       ▼
MongoDB Atlas (nubank_db.historico_diario)
  - Índice Único: (ticker, datetime)
  - Upsert idempotente (sem duplicatas)
       │
       ▼
Dashboard Interativo & GitHub Pages
  - Atualização periódica via GitHub Actions
  - Zero manipulação manual de arquivos!""",
            language="text",
        )
    with col2:
        st.markdown("### 📦 Estatísticas da Base de Dados")
        st.write(f"- **Status da Conexão:** {'Conectado ao Atlas' if is_connected else 'Modo Demonstração / Offline'}")
        st.write(f"- **Banco:** `nubank_db`")
        st.write(f"- **Coleção de Cotações:** `historico_diario`")
        st.write(f"- **Total de Registros Carregados:** {len(market_df)}")
        st.write(f"- **Tickers Coletados:** {', '.join(available_tickers)}")
        st.write(f"- **Agendamento Automático:** Segunda a Sexta às 22:00 UTC via GitHub Actions (`.github/workflows/coleta_diaria.yml`)")

st.markdown("---")
st.caption("Nubank 2.0 · Projeto Integrador 4 - Fatec Sebrae · Dados Twelve Data & Nu SEC Filings.")
