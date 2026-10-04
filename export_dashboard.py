import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# 🔧 Aqui você pode substituir por fetch_market_data() e fetch_fundamental_data()
# Para simplificar, vou usar dados fictícios
dates = pd.date_range("2024-01-01", periods=30, freq="D")
df = pd.DataFrame({
    "datetime": dates,
    "open": [10 + i*0.1 for i in range(30)],
    "high": [10.5 + i*0.1 for i in range(30)],
    "low": [9.5 + i*0.1 for i in range(30)],
    "close": [10 + i*0.1 for i in range(30)],
    "volume": [1000 + i*50 for i in range(30)],
})

# 📈 Gráfico Candlestick
fig_candle = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
fig_candle.add_trace(go.Candlestick(
    x=df["datetime"], open=df["open"], high=df["high"], low=df["low"], close=df["close"],
    name="OHLC"
), row=1, col=1)
fig_candle.add_trace(go.Bar(x=df["datetime"], y=df["volume"], name="Volume"), row=2, col=1)

# 📊 Gráfico de linha comparativo
fig_line = px.line(df, x="datetime", y="close", title="Preço de Fechamento")

# 💰 Gráfico de barras exemplo
fig_bar = px.bar(df, x="datetime", y="volume", title="Volume negociado")

# 🔗 Exportar todos em um único index.html
with open("index.html", "w", encoding="utf-8") as f:
    f.write("<html><head><title>Nubank 2.0 Dashboard</title></head><body>")
    f.write("<h1>📈 Nubank 2.0 Dashboard</h1>")
    f.write("<h2>Candlestick + Volume</h2>")
    f.write(fig_candle.to_html(full_html=False, include_plotlyjs="cdn"))
    f.write("<h2>Preço de Fechamento</h2>")
    f.write(fig_line.to_html(full_html=False, include_plotlyjs=False))
    f.write("<h2>Volume Negociado</h2>")
    f.write(fig_bar.to_html(full_html=False, include_plotlyjs=False))
    f.write("</body></html>")
