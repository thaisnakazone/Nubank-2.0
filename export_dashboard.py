from database.connection import get_database, get_mongo_client, get_mongo_uri
from src.data_pipeline import load_financial_history, load_capital_risk_history
import plotly.graph_objects as go
import plotly.express as px

# Dados do Atlas
financial = load_financial_history()
risk, risk_source = load_capital_risk_history()

# Gráfico Receita vs Lucro
fig_rev = go.Figure()
fig_rev.add_trace(go.Bar(x=financial.year, y=financial.revenue_usd_b, name="Receita"))
fig_rev.add_trace(go.Scatter(x=financial.year, y=financial.net_income_usd_b, name="Lucro líquido", mode="lines+markers"))

# Margens
financial["gross_margin"] = (financial["gross_profit_usd_b"] / financial["revenue_usd_b"]) * 100
financial["net_margin"] = (financial["net_income_usd_b"] / financial["revenue_usd_b"]) * 100
fig_margens = go.Figure()
fig_margens.add_trace(go.Scatter(x=financial.year, y=financial.gross_margin, name="Margem Bruta"))
fig_margens.add_trace(go.Scatter(x=financial.year, y=financial.net_margin, name="Margem Líquida"))

# Índices de Basileia
fig_risk = go.Figure()
fig_risk.add_trace(go.Scatter(x=risk.period, y=risk.basel_index_pct, name="Índice de Basileia"))
fig_risk.add_trace(go.Scatter(x=risk.period, y=risk.icp_pct, name="ICP"))

# Exportar para index.html
with open("index.html", "w", encoding="utf-8") as f:
    f.write("<html><head><title>Nubank 2.0 Dashboard</title></head><body>")
    f.write("<h1>📊 Nubank 2.0 · Dashboard</h1>")
    f.write("<h2>Receita vs Lucro Líquido</h2>")
    f.write(fig_rev.to_html(full_html=False, include_plotlyjs="cdn"))
    f.write("<h2>Margens</h2>")
    f.write(fig_margens.to_html(full_html=False, include_plotlyjs=False))
    f.write("<h2>Índices Prudenciais</h2>")
    f.write(fig_risk.to_html(full_html=False, include_plotlyjs=False))
    f.write("</body></html>")
