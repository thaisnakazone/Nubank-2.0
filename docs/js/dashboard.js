const PURPLE = '#820AD1';
const PURPLE_DARK = '#2F0549';
const PURPLE_MID = '#6B16A8';
const PURPLE_SOFT = '#C89BE5';
const MUTED = '#6F6673';
const GRID = '#ECE7EF';
const POSITIVE = '#157A54';
const NEGATIVE = '#B42318';

const plotConfig = {
  responsive: true,
  displaylogo: false,
  modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
  scrollZoom: false,
};

const baseLayout = {
  paper_bgcolor: 'rgba(0,0,0,0)',
  plot_bgcolor: 'rgba(0,0,0,0)',
  font: { family: 'Inter, Segoe UI, sans-serif', color: '#17131A', size: 12 },
  margin: { l: 55, r: 22, t: 22, b: 48 },
  hoverlabel: { bgcolor: '#2F0549', bordercolor: '#2F0549', font: { color: '#fff' } },
  xaxis: { gridcolor: GRID, zerolinecolor: GRID, fixedrange: true },
  yaxis: { gridcolor: GRID, zerolinecolor: GRID, fixedrange: true },
  legend: { orientation: 'h', x: 0, y: 1.12, bgcolor: 'rgba(0,0,0,0)' },
};

function layout(extra = {}) {
  return {
    ...baseLayout,
    ...extra,
    xaxis: { ...baseLayout.xaxis, ...(extra.xaxis || {}) },
    yaxis: { ...baseLayout.yaxis, ...(extra.yaxis || {}) },
    legend: { ...baseLayout.legend, ...(extra.legend || {}) },
  };
}

const fmt1 = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const fmt2 = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmt0 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 });

function usdB(value, digits = 2) {
  if (value == null) return '—';
  return `US$ ${digits === 1 ? fmt1.format(value) : fmt2.format(value)} bi`;
}

function pct(value, digits = 1) {
  if (value == null) return '—';
  const n = digits === 0 ? fmt0.format(value) : fmt1.format(value);
  return `${n}%`;
}

function values(rows, key) {
  return rows.map(row => row[key]);
}

function years(rows) {
  return rows.map(row => String(row.year));
}

function safePlot(id, traces, chartLayout) {
  const node = document.getElementById(id);
  if (!node || typeof Plotly === 'undefined') return;
  Plotly.newPlot(node, traces, chartLayout, plotConfig);
}

function renderHeadline(data) {
  const h = data.headline;
  document.getElementById('metric-customers').textContent = `${fmt1.format(h.customers_m)} mi`;
  document.getElementById('metric-customers-note').textContent = `+${fmt0.format(h.customer_growth_pct)}% desde 2021`;
  document.getElementById('metric-revenue').textContent = usdB(h.revenue_usd_b);
  document.getElementById('metric-revenue-note').textContent = `${fmt1.format(h.revenue_multiple)}× o nível de 2021`;
  document.getElementById('metric-income').textContent = usdB(h.net_income_usd_b);
  document.getElementById('metric-deposits').textContent = usdB(h.deposits_usd_b, 1);
  document.getElementById('metric-deposits-note').textContent = `${fmt1.format(h.deposit_multiple)}× o nível de 2021`;
}

function renderGrowth(data) {
  const f = data.financial;
  const x = years(f);

  safePlot('chart-revenue-income', [
    {
      type: 'bar', x, y: values(f, 'revenue_usd_b'), name: 'Receita', marker: { color: PURPLE },
      hovertemplate: '<b>%{x}</b><br>Receita: US$ %{y:.2f} bi<extra></extra>',
    },
    {
      type: 'scatter', mode: 'lines+markers', x, y: values(f, 'net_income_usd_b'), name: 'Lucro líquido',
      line: { color: PURPLE_DARK, width: 3 }, marker: { size: 8 },
      hovertemplate: '<b>%{x}</b><br>Lucro líquido: US$ %{y:.2f} bi<extra></extra>',
    },
  ], layout({ yaxis: { title: 'US$ bilhões', gridcolor: GRID, zerolinecolor: '#BEB6C2' }, barmode: 'overlay' }));

  safePlot('chart-scale', [
    {
      type: 'scatter', mode: 'lines+markers', x, y: values(f, 'customers_m'), name: 'Clientes',
      line: { color: PURPLE, width: 4 }, marker: { size: 8 },
      hovertemplate: '<b>%{x}</b><br>Clientes: %{y:.1f} mi<extra></extra>',
    },
    {
      type: 'bar', x, y: values(f, 'deposits_usd_b'), name: 'Depósitos', yaxis: 'y2', opacity: .58,
      marker: { color: PURPLE_SOFT },
      hovertemplate: '<b>%{x}</b><br>Depósitos: US$ %{y:.1f} bi<extra></extra>',
    },
  ], layout({
    yaxis: { title: 'Clientes (milhões)', gridcolor: GRID },
    yaxis2: { title: 'Depósitos (US$ bi)', overlaying: 'y', side: 'right', gridcolor: 'rgba(0,0,0,0)', fixedrange: true },
  }));

  safePlot('chart-arpac', [
    {
      type: 'scatter', mode: 'lines+markers', x, y: values(f, 'arpac_usd'), name: 'ARPAC mensal',
      line: { color: PURPLE, width: 4 }, marker: { size: 8 },
      hovertemplate: '<b>%{x}</b><br>ARPAC: US$ %{y:.1f}<extra></extra>',
    },
    {
      type: 'scatter', mode: 'lines+markers', x, y: values(f, 'cost_to_serve_usd'), name: 'Custo de servir',
      line: { color: '#7B7480', width: 2.5, dash: 'dot' }, marker: { size: 7 },
      hovertemplate: '<b>%{x}</b><br>Custo: US$ %{y:.1f}<extra></extra>',
    },
  ], layout({ yaxis: { title: 'US$ / cliente ativo / mês', gridcolor: GRID } }));

  const portfolio = f.filter(row => row.credit_portfolio_usd_b != null);
  safePlot('chart-portfolio', [
    {
      type: 'bar', x: years(portfolio), y: values(portfolio, 'credit_portfolio_usd_b'), name: 'Cartão + empréstimos pessoais',
      marker: { color: PURPLE }, hovertemplate: '<b>%{x}</b><br>US$ %{y:.1f} bi<extra></extra>',
    },
    {
      type: 'bar', x: years(portfolio), y: values(portfolio, 'interest_earning_portfolio_usd_b'), name: 'Carteira geradora de juros',
      marker: { color: '#D9B9ED' }, hovertemplate: '<b>%{x}</b><br>US$ %{y:.1f} bi<extra></extra>',
    },
  ], layout({ barmode: 'group', yaxis: { title: 'US$ bilhões', gridcolor: GRID } }));

  const first = f[0];
  const last = f[f.length - 1];
  const arpacGrowth = (last.arpac_usd / first.arpac_usd - 1) * 100;
  const insights = [
    ['Receita', `${fmt1.format(last.revenue_usd_b / first.revenue_usd_b)}×`, `${usdB(first.revenue_usd_b)} → ${usdB(last.revenue_usd_b)}`],
    ['Clientes', `${fmt1.format(last.customers_m / first.customers_m)}×`, `${fmt1.format(first.customers_m)} mi → ${fmt1.format(last.customers_m)} mi`],
    ['ARPAC mensal', `+${fmt0.format(arpacGrowth)}%`, `US$ ${fmt1.format(first.arpac_usd)} → US$ ${fmt1.format(last.arpac_usd)}`],
  ];
  document.getElementById('growth-insights').innerHTML = insights.map(([label, value, note]) => `
    <div class="insight"><span>${label}</span><strong>${value}</strong><p>${note}</p></div>
  `).join('');
}

function renderProfitability(data) {
  const f = data.financial;
  const x = years(f);
  const income = values(f, 'net_income_usd_b');

  safePlot('chart-income', [{
    type: 'bar', x, y: income,
    marker: { color: income.map(v => v < 0 ? NEGATIVE : POSITIVE) },
    text: income.map(v => usdB(v)), textposition: 'outside', cliponaxis: false,
    hovertemplate: '<b>%{x}</b><br>Lucro líquido: US$ %{y:.2f} bi<extra></extra>',
  }], layout({ showlegend: false, yaxis: { title: 'US$ bilhões', gridcolor: GRID, zerolinecolor: '#BEB6C2' } }));

  const grossMargin = f.map(row => row.gross_profit_usd_b / row.revenue_usd_b * 100);
  const netMargin = f.map(row => row.net_income_usd_b / row.revenue_usd_b * 100);
  safePlot('chart-margins', [
    {
      type: 'scatter', mode: 'lines+markers', x, y: grossMargin, name: 'Margem bruta',
      line: { color: PURPLE, width: 4 }, marker: { size: 8 }, hovertemplate: '<b>%{x}</b><br>Margem bruta: %{y:.1f}%<extra></extra>',
    },
    {
      type: 'scatter', mode: 'lines+markers', x, y: netMargin, name: 'Margem líquida',
      line: { color: PURPLE_DARK, width: 3 }, marker: { size: 8 }, hovertemplate: '<b>%{x}</b><br>Margem líquida: %{y:.1f}%<extra></extra>',
    },
  ], layout({ yaxis: { title: '% da receita', ticksuffix: '%', gridcolor: GRID, zerolinecolor: '#BEB6C2' } }));

  const firstPositive = f.find(row => row.net_income_usd_b > 0);
  const latest = f[f.length - 1];
  document.getElementById('profit-insight').innerHTML = firstPositive
    ? `<strong>Ponto de inflexão:</strong> o lucro líquido IFRS passa ao campo positivo em <b>${firstPositive.year}</b> e alcança <b>${usdB(latest.net_income_usd_b)}</b> em ${latest.year}.`
    : '<strong>Leitura:</strong> a série selecionada ainda não apresenta lucro líquido positivo.';
}

function renderRisk(data) {
  const risk = data.risk.filter(row => row.period);
  document.getElementById('risk-source').textContent = data.meta.risk_source || 'Pilar 3 · dados regulatórios locais';
  const x = risk.map(row => row.period);

  safePlot('chart-capital', [
    {
      type: 'scatter', mode: 'lines+markers', x, y: values(risk, 'capital_principal_brl_b'), name: 'Capital Principal',
      connectgaps: false, line: { color: PURPLE, width: 4 }, marker: { size: 7 },
      hovertemplate: '<b>%{x|%m/%Y}</b><br>Capital Principal: R$ %{y:.1f} bi<extra></extra>',
    },
    {
      type: 'scatter', mode: 'lines+markers', x, y: values(risk, 'rwa_total_brl_b'), name: 'RWA total',
      connectgaps: false, line: { color: PURPLE_DARK, width: 3 }, marker: { size: 7 },
      hovertemplate: '<b>%{x|%m/%Y}</b><br>RWA total: R$ %{y:.1f} bi<extra></extra>',
    },
  ], layout({ yaxis: { title: 'R$ bilhões', gridcolor: GRID }, xaxis: { gridcolor: GRID, type: 'date' } }));

  safePlot('chart-prudential', [
    {
      type: 'scatter', mode: 'lines+markers', x, y: values(risk, 'basel_index_pct'), name: 'Índice de Basileia',
      connectgaps: false, line: { color: PURPLE, width: 4 }, marker: { size: 7 },
      hovertemplate: '<b>%{x|%m/%Y}</b><br>Basileia: %{y:.2f}%<extra></extra>',
    },
    {
      type: 'scatter', mode: 'lines+markers', x, y: values(risk, 'icp_pct'), name: 'ICP',
      connectgaps: false, line: { color: PURPLE_SOFT, width: 3, dash: 'dot' }, marker: { size: 7 },
      hovertemplate: '<b>%{x|%m/%Y}</b><br>ICP: %{y:.2f}%<extra></extra>',
    },
  ], layout({ yaxis: { title: '%', ticksuffix: '%', gridcolor: GRID }, xaxis: { gridcolor: GRID, type: 'date' } }));

  const detail = data.risk_2025;
  safePlot('chart-credit-risk', [{
    type: 'bar', x: values(detail, 'quarter'), y: values(detail, 'rwa_credito_brl_b'),
    marker: { color: PURPLE }, text: values(detail, 'rwa_credito_brl_b').map(v => `R$ ${fmt1.format(v)} bi`), textposition: 'outside',
    hovertemplate: '<b>%{x}</b><br>RWA crédito: R$ %{y:.1f} bi<extra></extra>',
  }], layout({ showlegend: false, yaxis: { title: 'R$ bilhões', gridcolor: GRID } }));

  safePlot('chart-market-risk', [
    {
      type: 'bar', x: values(detail, 'quarter'), y: values(detail, 'rwa_juros_brl_m'), name: 'Juros', marker: { color: PURPLE_MID },
      hovertemplate: '<b>%{x}</b><br>Juros: R$ %{y:.1f} mi<extra></extra>',
    },
    {
      type: 'bar', x: values(detail, 'quarter'), y: values(detail, 'rwa_cambio_brl_m'), name: 'Câmbio', marker: { color: '#D8AFE9' },
      hovertemplate: '<b>%{x}</b><br>Câmbio: R$ %{y:.1f} mi<extra></extra>',
    },
  ], layout({ barmode: 'group', yaxis: { title: 'R$ milhões', gridcolor: GRID } }));

  if (detail.length >= 2) {
    const latest = detail[detail.length - 1];
    const prior = detail[detail.length - 2];
    const multiple = latest.rwa_cambio_brl_m / prior.rwa_cambio_brl_m;
    document.getElementById('risk-insight').innerHTML = `<strong>Sinal para investigação:</strong> no recorte disponível, o RWA cambial de ${latest.quarter}/2025 é <b>${fmt1.format(multiple)}×</b> o valor de ${prior.quarter}. A análise destaca a mudança, mas não atribui causalidade sem suporte das notas regulatórias.`;
  }
}

function renderCustomer(data) {
  const c = data.customer;
  document.getElementById('customer-total').textContent = fmt0.format(c.total);
  document.getElementById('customer-loss').textContent = c.loss_share_pct == null ? '—' : pct(c.loss_share_pct);
  document.getElementById('customer-security').textContent = c.security_signals == null ? '—' : fmt0.format(c.security_signals);

  const categories = [...c.categories].sort((a, b) => a.reclamacoes - b.reclamacoes);
  safePlot('chart-categories', [{
    type: 'bar', orientation: 'h', x: values(categories, 'reclamacoes'), y: values(categories, 'categoria'),
    marker: { color: PURPLE }, text: values(categories, 'reclamacoes'), textposition: 'outside', cliponaxis: false,
    hovertemplate: '<b>%{y}</b><br>%{x} reclamações<extra></extra>',
  }], layout({ showlegend: false, margin: { l: 150, r: 38, t: 22, b: 45 }, xaxis: { title: 'Reclamações', gridcolor: GRID } }));

  safePlot('chart-severity', [{
    type: 'pie', labels: values(c.severity, 'severidade'), values: values(c.severity, 'reclamacoes'), hole: .58,
    marker: { colors: [PURPLE_DARK, PURPLE, PURPLE_SOFT, '#E9D9F1'] }, textinfo: 'percent',
    hovertemplate: '<b>%{label}</b><br>%{value} reclamações · %{percent}<extra></extra>',
  }], layout({ margin: { l: 20, r: 20, t: 20, b: 35 }, legend: { orientation: 'h', x: 0, y: -.05 } }));

  safePlot('chart-clusters', [{
    type: 'bar', x: values(c.clusters, 'cluster').map(String), y: values(c.clusters, 'reclamacoes'),
    marker: { color: PURPLE_MID }, text: values(c.clusters, 'reclamacoes'), textposition: 'outside',
    hovertemplate: '<b>Cluster %{x}</b><br>%{y} reclamações<extra></extra>',
  }], layout({ showlegend: false, xaxis: { title: 'Cluster', gridcolor: GRID }, yaxis: { title: 'Reclamações', gridcolor: GRID } }));
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[char]));
}

function renderSources(data) {
  const body = document.getElementById('source-table');
  body.innerHTML = data.sources.map(row => `
    <tr>
      <td><strong>${escapeHtml(row.dataset)}</strong></td>
      <td>${escapeHtml(row.period)}</td>
      <td>${escapeHtml(row.source_type)}</td>
      <td>${escapeHtml(row.source)}</td>
    </tr>
  `).join('');
}

function renderMarket(data) {
  if (!data.market || !data.market.length) return;

  const marketPill = document.getElementById('market-source-pill');
  if (marketPill && data.meta && data.meta.market_source) {
    marketPill.textContent = data.meta.market_source;
  }

  const nuRows = data.market.filter(r => r.ticker === 'NU').sort((a, b) => a.datetime.localeCompare(b.datetime));
  if (nuRows.length) {
    const latest = nuRows[nuRows.length - 1];
    const first = nuRows[0];
    const varPct = ((latest.close / first.close) - 1) * 100;
    const volSum = nuRows.reduce((acc, r) => acc + (r.volume || 0), 0);
    const volAvg = volSum / nuRows.length;

    const closeElem = document.getElementById('market-nu-close');
    if (closeElem) closeElem.textContent = `US$ ${fmt2.format(latest.close)}`;

    const dateElem = document.getElementById('market-nu-date');
    if (dateElem) dateElem.textContent = `Pregão: ${latest.datetime}`;

    const varElem = document.getElementById('market-nu-var');
    if (varElem) {
      varElem.textContent = `${varPct >= 0 ? '+' : ''}${fmt2.format(varPct)}%`;
      varElem.style.color = varPct >= 0 ? POSITIVE : NEGATIVE;
    }

    const volElem = document.getElementById('market-nu-vol');
    if (volElem) volElem.textContent = `${fmt1.format(volAvg / 1e6)}M`;

    const xDates = nuRows.map(r => r.datetime);
    const yCloses = nuRows.map(r => r.close);
    const yVolumes = nuRows.map(r => r.volume);

    safePlot('chart-market-nu', [
      {
        type: 'scatter',
        mode: 'lines+markers',
        x: xDates,
        y: yCloses,
        name: 'Fechamento NU',
        line: { color: PURPLE, width: 3 },
        marker: { size: 6 },
        hovertemplate: '<b>%{x}</b><br>Fechamento: US$ %{y:.2f}<extra></extra>',
      },
      {
        type: 'bar',
        x: xDates,
        y: yVolumes,
        name: 'Volume',
        yaxis: 'y2',
        opacity: 0.35,
        marker: { color: PURPLE_SOFT },
        hovertemplate: '<b>%{x}</b><br>Volume: %{y:,.0f}<extra></extra>',
      },
    ], layout({
      yaxis: { title: 'Preço (US$)', gridcolor: GRID },
      yaxis2: { title: 'Volume', overlaying: 'y', side: 'right', gridcolor: 'rgba(0,0,0,0)', fixedrange: true },
      legend: { orientation: 'h', x: 0, y: 1.12 },
    }));
  }

  const tickers = ['NU', 'ITUB', 'BBD'];
  const traces = [];
  const colorMap = { NU: PURPLE, ITUB: '#FF7A00', BBD: '#D62828' };

  for (const ticker of tickers) {
    const tRows = data.market.filter(r => r.ticker === ticker).sort((a, b) => a.datetime.localeCompare(b.datetime));
    if (tRows.length > 0) {
      const baseClose = tRows[0].close;
      const normValues = tRows.map(r => (r.close / baseClose) * 100);
      traces.push({
        type: 'scatter',
        mode: 'lines+markers',
        x: tRows.map(r => r.datetime),
        y: normValues,
        name: ticker,
        line: { color: colorMap[ticker] || '#666', width: ticker === 'NU' ? 3.5 : 2 },
        marker: { size: 5 },
        hovertemplate: `<b>%{x}</b><br>${ticker}: %{y:.1f} (base 100)<extra></extra>`,
      });
    }
  }

  if (traces.length) {
    safePlot('chart-market-comparison', traces, layout({
      yaxis: { title: 'Base 100 = 1º pregão', gridcolor: GRID },
      legend: { orientation: 'h', x: 0, y: 1.12 },
    }));
  }
}

async function init() {
  try {
    const response = await fetch('data/dashboard-data.json', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();

    renderHeadline(data);
    renderMarket(data);
    renderGrowth(data);
    renderProfitability(data);
    renderRisk(data);
    renderCustomer(data);
    renderSources(data);
  } catch (error) {
    console.error('Falha ao carregar dashboard:', error);
    document.getElementById('load-error').hidden = false;
  }
}

document.addEventListener('DOMContentLoaded', init);
