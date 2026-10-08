/* =========================================================
   Nubank em Dados 2.0 — dashboard estático (GitHub Pages)
   Lê docs/data/dashboard-data.json, gerado por src/build_web_data.py
   ========================================================= */

// ---------- Paletas (validadas para daltonismo, claro e escuro) ----------
const PALETTE = {
  light: {
    NU: '#820AD1', ITUB: '#E26B00', BBD: '#CC092F',
    nuSoft: '#C9A2EC', nuDeep: '#2F0549', neutral: '#8A818F',
    positive: '#127A50', negative: '#B42318',
    ink: '#1B1520', muted: '#6F6675', grid: '#ECE6F0', axis: '#D6CBDD',
    hoverBg: '#2F0549', hoverInk: '#FFFFFF',
  },
  dark: {
    NU: '#A55EEA', ITUB: '#D97706', BBD: '#E0263F',
    nuSoft: '#6E3D9C', nuDeep: '#E2C8F7', neutral: '#9C92A3',
    positive: '#3ECF8E', negative: '#FF6B6B',
    ink: '#F2EDF5', muted: '#A59BAB', grid: '#2B2232', axis: '#44394D',
    hoverBg: '#F2EDF5', hoverInk: '#1B1520',
  },
};
// Codificação secundária (além da cor) para cada banco
const DASH = { NU: 'solid', ITUB: 'dash', BBD: 'dot' };
const TICKER_NAMES = { NU: 'Nubank', ITUB: 'Itaú', BBD: 'Bradesco' };
const TICKER_ORDER = ['NU', 'ITUB', 'BBD'];

const state = {
  data: null,
  tab: 'mercado',
  ticker: 'NU',
  range: 0,
  style: 'candle',
  rendered: new Set(),
};

// ---------- Utilidades ----------
const fmt0 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 });
const fmt1 = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const fmt2 = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const usdB = (v, d = 2) => (v == null ? '—' : `US$ ${(d === 1 ? fmt1 : fmt2).format(v)} bi`);
const pct = (v, d = 1) => (v == null ? '—' : `${(d === 0 ? fmt0 : d === 2 ? fmt2 : fmt1).format(v)}%`);
const signed = (v) => `${v >= 0 ? '+' : '−'}${fmt2.format(Math.abs(v))}%`;
const values = (rows, key) => rows.map((r) => r[key]);
const years = (rows) => rows.map((r) => String(r.year));
const $ = (id) => document.getElementById(id);
const setText = (id, text) => { const n = $(id); if (n) n.textContent = text; };
const dateBR = (iso) => { if (!iso) return '—'; const [y, m, d] = iso.slice(0, 10).split('-'); return `${d}/${m}/${y}`; };

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));
}

// ---------- Tema ----------
function currentMode() {
  const forced = document.documentElement.dataset.theme;
  if (forced === 'dark' || forced === 'light') return forced;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}
const C = () => PALETTE[currentMode()];

function setupThemeToggle() {
  $('theme-toggle').addEventListener('click', () => {
    const next = currentMode() === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('nu-theme', next); } catch (e) { /* ignora */ }
    rerenderAll();
  });
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (!document.documentElement.dataset.theme) rerenderAll();
  });
}

// ---------- Plotly ----------
const plotConfig = {
  responsive: true,
  displaylogo: false,
  modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d', 'toggleSpikelines'],
  scrollZoom: false,
  locale: 'pt-BR',
};

function layout(extra = {}) {
  const c = C();
  const axis = {
    gridcolor: c.grid, linecolor: c.axis, zerolinecolor: c.axis, tickcolor: c.axis,
    tickfont: { color: c.muted, size: 11 }, title: { font: { color: c.muted, size: 11 } },
    automargin: true, fixedrange: true,
  };
  const merge = (base, over) => ({ ...base, ...(over || {}), title: typeof over?.title === 'string' ? { text: over.title, font: base.title.font } : (over?.title || base.title) });
  return {
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: { family: 'Manrope, Segoe UI, sans-serif', color: c.ink, size: 12 },
    margin: { l: 8, r: 12, t: 12, b: 8 },
    hoverlabel: { bgcolor: c.hoverBg, bordercolor: c.hoverBg, font: { color: c.hoverInk, family: 'Manrope, sans-serif' } },
    legend: { orientation: 'h', x: 0, y: 1.14, font: { color: c.ink }, bgcolor: 'rgba(0,0,0,0)' },
    barcornerradius: 4,
    bargap: 0.32,
    separators: ',.',
    ...extra,
    xaxis: merge({ ...axis, showgrid: false }, extra.xaxis),
    yaxis: merge(axis, extra.yaxis),
  };
}

function plot(id, traces, chartLayout) {
  const node = $(id);
  if (!node || typeof Plotly === 'undefined') return;
  Plotly.react(node, traces, chartLayout, plotConfig);
}

// ---------- Cabeçalho ----------
function renderHeader(d) {
  const h = d.headline;
  setText('kpi-customers', `${fmt1.format(h.customers_m)} mi`);
  setText('kpi-customers-note', `+${fmt0.format(h.customer_growth_pct)}% desde 2021`);
  setText('kpi-revenue', usdB(h.revenue_usd_b));
  setText('kpi-revenue-note', `${fmt1.format(h.revenue_multiple)}× o nível de 2021`);
  setText('kpi-income', usdB(h.net_income_usd_b));
  setText('kpi-income-note', `IFRS · ${h.latest_year}`);

  const updated = d.meta.updated_at || '';
  setText('meta-updated', updated ? `${dateBR(updated)} · ${updated.slice(11, 16)} UTC` : '—');
  setText('meta-period', d.meta.period || '—');

  const src = d.meta.market_source || '';
  const chip = $('status-chip');
  const demo = /demonstra|amostra/i.test(src);
  chip.classList.add(demo ? 'demo' : 'online');
  setText('status-text', demo ? 'Cotações de demonstração' : 'MongoDB Atlas · dados reais');
  chip.title = src;

  const nu = seriesFor('NU');
  if (nu.length) {
    const last = nu[nu.length - 1];
    const prev = nu[nu.length - 2];
    setText('kpi-nu', `US$ ${fmt2.format(last.close)}`);
    const note = $('kpi-nu-note');
    if (prev) {
      const dv = (last.close / prev.close - 1) * 100;
      note.textContent = `${signed(dv)} no dia · ${dateBR(last.datetime)}`;
      note.className = `kpi-note ${dv >= 0 ? 'up' : 'down'}`;
    }
  }
}

// ---------- Mercado ----------
function seriesFor(ticker) {
  return (state.data.market || [])
    .filter((r) => r.ticker === ticker)
    .sort((a, b) => a.datetime.localeCompare(b.datetime));
}

function sma(rows, n) {
  return rows.map((_, i) => {
    if (i < n - 1) return null;
    let s = 0;
    for (let k = i - n + 1; k <= i; k += 1) s += rows[k].close;
    return s / n;
  });
}

function sliceRange(arr) {
  return state.range > 0 ? arr.slice(-state.range) : arr;
}

function setupMarketControls() {
  const tickers = TICKER_ORDER.filter((t) => seriesFor(t).length);
  $('ticker-picker').innerHTML = tickers.map((t) => `
    <button role="radio" data-ticker="${t}" title="${TICKER_NAMES[t]}">
      <span class="swatch" data-swatch="${t}"></span>${t}
    </button>`).join('');

  const bind = (groupId, key, attr, parse = (v) => v) => {
    const group = $(groupId);
    const sync = () => group.querySelectorAll('button').forEach((b) => {
      b.setAttribute('aria-checked', String(parse(b.dataset[attr]) === state[key]));
      b.tabIndex = parse(b.dataset[attr]) === state[key] ? 0 : -1;
    });
    group.addEventListener('click', (e) => {
      const btn = e.target.closest('button');
      if (!btn) return;
      state[key] = parse(btn.dataset[attr]);
      sync();
      renderMarket();
    });
    group.addEventListener('keydown', (e) => {
      if (!['ArrowLeft', 'ArrowRight'].includes(e.key)) return;
      const btns = [...group.querySelectorAll('button')];
      const i = btns.findIndex((b) => b.getAttribute('aria-checked') === 'true');
      const next = btns[(i + (e.key === 'ArrowRight' ? 1 : btns.length - 1)) % btns.length];
      next.click(); next.focus();
    });
    sync();
  };
  bind('ticker-picker', 'ticker', 'ticker');
  bind('range-picker', 'range', 'range', Number);
  bind('style-picker', 'style', 'style');
}

function paintSwatches() {
  const c = C();
  document.querySelectorAll('[data-swatch]').forEach((s) => { s.style.background = c[s.dataset.swatch]; });
}

function renderMarket() {
  const c = C();
  paintSwatches();
  setText('market-source', `Fonte: ${state.data.meta.market_source || '—'}`);

  const full = seriesFor(state.ticker);
  if (!full.length) return;
  const s7 = sma(full, 7);
  const s21 = sma(full, 21);
  const rows = sliceRange(full);
  const offset = full.length - rows.length;
  const x = values(rows, 'datetime');
  const first = rows[0];
  const last = rows[rows.length - 1];
  const varPct = (last.close / first.close - 1) * 100;
  const lo = Math.min(...values(rows, 'low'));
  const hi = Math.max(...values(rows, 'high'));
  const volAvg = rows.reduce((a, r) => a + (r.volume || 0), 0) / rows.length;

  setText('mk-close', `US$ ${fmt2.format(last.close)}`);
  setText('mk-close-note', `${state.ticker} · pregão de ${dateBR(last.datetime)}`);
  setText('mk-var', signed(varPct));
  $('mk-var').className = varPct >= 0 ? 'up' : 'down';
  setText('mk-var-note', `desde ${dateBR(first.datetime)}`);
  setText('mk-range', `${fmt2.format(lo)} – ${fmt2.format(hi)}`);
  setText('mk-range-note', `amplitude de US$ ${fmt2.format(hi - lo)}`);
  setText('mk-vol', volAvg >= 1e6 ? `${fmt1.format(volAvg / 1e6)} mi` : fmt0.format(volAvg));
  setText('price-title', `${TICKER_NAMES[state.ticker]} (${state.ticker}) · preço e médias móveis`);

  const xaxis = { type: 'date', tickformat: '%d/%m', rangebreaks: [{ bounds: ['sat', 'mon'] }], showgrid: false };
  const priceTrace = state.style === 'candle'
    ? {
      type: 'candlestick', x, open: values(rows, 'open'), high: values(rows, 'high'), low: values(rows, 'low'), close: values(rows, 'close'),
      name: state.ticker,
      increasing: { line: { color: c.positive, width: 1.2 }, fillcolor: c.positive },
      decreasing: { line: { color: c.negative, width: 1.2 }, fillcolor: c.negative },
      hoverinfo: 'x+text',
      text: rows.map((r) => `Abertura ${fmt2.format(r.open)} · Máx ${fmt2.format(r.high)}<br>Mín ${fmt2.format(r.low)} · Fech. ${fmt2.format(r.close)}`),
    }
    : {
      type: 'scatter', mode: 'lines', x, y: values(rows, 'close'), name: 'Fechamento',
      line: { color: c[state.ticker], width: 2.5 }, fill: 'tozeroy',
      fillcolor: `${c[state.ticker]}14`,
      hovertemplate: 'Fechamento: US$ %{y:.2f}<extra></extra>',
    };
  const yLine = state.style === 'line' ? { range: [lo * 0.97, hi * 1.02] } : {};

  plot('chart-price', [
    priceTrace,
    {
      type: 'scatter', mode: 'lines', x, y: s7.slice(offset), name: 'Média 7d',
      line: { color: c.nuDeep, width: 2 }, connectgaps: false,
      hovertemplate: 'Média 7d: US$ %{y:.2f}<extra></extra>',
    },
    {
      type: 'scatter', mode: 'lines', x, y: s21.slice(offset), name: 'Média 21d',
      line: { color: c.neutral, width: 2, dash: 'dash' }, connectgaps: false,
      hovertemplate: 'Média 21d: US$ %{y:.2f}<extra></extra>',
    },
  ], layout({
    hovermode: 'x unified',
    xaxis: { ...xaxis, rangeslider: { visible: false }, showticklabels: false },
    yaxis: { title: 'US$', tickprefix: '', ...yLine },
    margin: { l: 8, r: 12, t: 30, b: 0 },
  }));

  plot('chart-volume', [{
    type: 'bar', x, y: values(rows, 'volume'), name: 'Volume',
    marker: { color: rows.map((r) => (r.close >= r.open ? c.positive : c.negative)), opacity: 0.55 },
    hovertemplate: '%{x|%d/%m/%Y}<br>Volume: %{y:,.0f}<extra></extra>',
  }], layout({
    showlegend: false,
    xaxis,
    yaxis: { title: 'Volume', tickformat: '.2s', nticks: 3 },
    margin: { l: 8, r: 12, t: 4, b: 8 },
  }));

  renderCompare();
}

function renderCompare() {
  const c = C();
  const traces = [];
  const annotations = [];
  const tableRows = [];
  TICKER_ORDER.forEach((t) => {
    const rows = sliceRange(seriesFor(t));
    if (!rows.length) return;
    const base = rows[0].close;
    const y = rows.map((r) => (r.close / base) * 100);
    const selected = t === state.ticker;
    traces.push({
      type: 'scatter', mode: 'lines', x: values(rows, 'datetime'), y, name: `${t} · ${TICKER_NAMES[t]}`,
      line: { color: c[t], width: selected ? 3 : 2, dash: DASH[t] },
      opacity: selected ? 1 : 0.85,
      hovertemplate: `${t}: %{y:.1f}<extra></extra>`,
    });
    const last = rows[rows.length - 1];
    const ret = y[y.length - 1] - 100;
    annotations.push({
      x: last.datetime, y: y[y.length - 1], xanchor: 'left', yanchor: 'middle', xshift: 6,
      text: `<b>${t}</b> ${signed(ret)}`, showarrow: false, font: { color: c.ink, size: 11 },
    });
    tableRows.push(`
      <tr>
        <td><span class="tk"><span class="swatch" style="background:${c[t]}"></span>${t} <small>${TICKER_NAMES[t]}</small></span></td>
        <td class="num">US$ ${fmt2.format(last.close)}</td>
        <td class="num ${ret >= 0 ? 'up' : 'down'}">${signed(ret)}</td>
      </tr>`);
  });
  $('ticker-table').innerHTML = tableRows.join('');

  // Evita sobreposição dos rótulos no fim das linhas (afasta em pixels)
  const node = $('chart-compare');
  const h = (node && node.clientHeight) || 320;
  const ys = traces.flatMap((t) => t.y);
  const span = (Math.max(...ys) - Math.min(...ys)) || 1;
  const pxPerUnit = (h - 70) / span;
  const order = annotations.map((a, i) => i).sort((a, b) => annotations[b].y - annotations[a].y);
  let prevPx = null;
  order.forEach((i) => {
    const a = annotations[i];
    let px = -a.y * pxPerUnit;
    if (prevPx != null && px - prevPx < 15) px = prevPx + 15;
    a.yshift = -(px - (-a.y * pxPerUnit));
    prevPx = px;
  });

  const narrow = window.innerWidth < 640;
  plot('chart-compare', traces, layout({
    hovermode: 'x unified',
    showlegend: !narrow, // no celular, os rótulos diretos + tabela já identificam as linhas
    annotations,
    shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 100, y1: 100, line: { color: c.axis, width: 1, dash: 'dot' } }],
    xaxis: { type: 'date', tickformat: '%d/%m', rangebreaks: [{ bounds: ['sat', 'mon'] }] },
    yaxis: { title: 'Base 100' },
    margin: { l: 8, r: 92, t: 30, b: 8 },
  }));
}

// ---------- Crescimento ----------
function renderGrowth() {
  const c = C();
  const f = state.data.financial;
  const x = years(f);

  plot('chart-revenue-income', [
    {
      type: 'bar', x, y: values(f, 'revenue_usd_b'), name: 'Receita', marker: { color: c.NU },
      hovertemplate: 'Receita: US$ %{y:.2f} bi<extra></extra>',
    },
    {
      type: 'scatter', mode: 'lines+markers', x, y: values(f, 'net_income_usd_b'), name: 'Lucro líquido',
      line: { color: c.nuDeep, width: 2.5 }, marker: { size: 9, color: c.nuDeep, line: { color: c.hoverInk === '#FFFFFF' ? '#fff' : '#1b1520', width: 2 } },
      hovertemplate: 'Lucro: US$ %{y:.2f} bi<extra></extra>',
    },
  ], layout({ hovermode: 'x unified', yaxis: { title: 'US$ bi', zeroline: true } }));

  plot('chart-arpac', [
    {
      type: 'scatter', mode: 'lines+markers+text', x, y: values(f, 'arpac_usd'), name: 'ARPAC mensal',
      line: { color: c.NU, width: 2.5 }, marker: { size: 9 },
      text: values(f, 'arpac_usd').map((v, i, a) => (i === a.length - 1 ? `US$ ${fmt1.format(v)}` : '')), textposition: 'top center',
      textfont: { color: c.ink },
      hovertemplate: 'ARPAC: US$ %{y:.1f}<extra></extra>',
    },
    {
      type: 'scatter', mode: 'lines+markers', x, y: values(f, 'cost_to_serve_usd'), name: 'Custo de servir',
      line: { color: c.neutral, width: 2, dash: 'dash' }, marker: { size: 8 },
      hovertemplate: 'Custo: US$ %{y:.1f}<extra></extra>',
    },
  ], layout({ hovermode: 'x unified', yaxis: { title: 'US$ / cliente / mês', rangemode: 'tozero' } }));

  plot('chart-customers', [{
    type: 'bar', x, y: values(f, 'customers_m'), name: 'Clientes', marker: { color: c.NU },
    text: values(f, 'customers_m').map((v) => fmt1.format(v)), textposition: 'outside', cliponaxis: false, textfont: { color: c.ink },
    hovertemplate: '%{x}: %{y:.1f} mi de clientes<extra></extra>',
  }], layout({ showlegend: false, yaxis: { title: 'milhões' }, margin: { l: 8, r: 12, t: 22, b: 8 } }));

  plot('chart-deposits', [{
    type: 'bar', x, y: values(f, 'deposits_usd_b'), name: 'Depósitos', marker: { color: c.nuSoft },
    text: values(f, 'deposits_usd_b').map((v) => fmt1.format(v)), textposition: 'outside', cliponaxis: false, textfont: { color: c.ink },
    hovertemplate: '%{x}: US$ %{y:.1f} bi<extra></extra>',
  }], layout({ showlegend: false, yaxis: { title: 'US$ bi' }, margin: { l: 8, r: 12, t: 22, b: 8 } }));

  const p = f.filter((r) => r.credit_portfolio_usd_b != null);
  plot('chart-portfolio', [
    {
      type: 'bar', x: years(p), y: values(p, 'credit_portfolio_usd_b'), name: 'Cartão + empréstimos pessoais',
      marker: { color: c.NU }, hovertemplate: 'Cartão + empréstimos: US$ %{y:.1f} bi<extra></extra>',
    },
    {
      type: 'bar', x: years(p), y: values(p, 'interest_earning_portfolio_usd_b'), name: 'Carteira geradora de juros',
      marker: { color: c.nuSoft }, hovertemplate: 'Geradora de juros: US$ %{y:.1f} bi<extra></extra>',
    },
  ], layout({ barmode: 'group', bargroupgap: 0.08, hovermode: 'x unified', yaxis: { title: 'US$ bi' } }));

  const first = f[0];
  const last = f[f.length - 1];
  const items = [
    ['Receita', `${fmt1.format(last.revenue_usd_b / first.revenue_usd_b)}×`, `${usdB(first.revenue_usd_b)} → ${usdB(last.revenue_usd_b)}`],
    ['Clientes', `${fmt1.format(last.customers_m / first.customers_m)}×`, `${fmt1.format(first.customers_m)} mi → ${fmt1.format(last.customers_m)} mi`],
    ['ARPAC mensal', `+${fmt0.format((last.arpac_usd / first.arpac_usd - 1) * 100)}%`, `US$ ${fmt1.format(first.arpac_usd)} → US$ ${fmt1.format(last.arpac_usd)}`],
  ];
  $('growth-insights').innerHTML = items.map(([l, v, n]) => `<div class="insight"><span>${l} · ${first.year}→${last.year}</span><strong>${v}</strong><p>${n}</p></div>`).join('');
}

// ---------- Rentabilidade ----------
function renderProfitability() {
  const c = C();
  const f = state.data.financial;
  const x = years(f);
  const income = values(f, 'net_income_usd_b');

  plot('chart-income', [{
    type: 'bar', x, y: income, marker: { color: income.map((v) => (v < 0 ? c.negative : c.positive)) },
    text: income.map((v) => `${v < 0 ? '−' : ''}${fmt2.format(Math.abs(v))}`), textposition: 'outside', cliponaxis: false,
    textfont: { color: c.ink },
    hovertemplate: '%{x}: US$ %{y:.2f} bi<extra></extra>',
  }], layout({ showlegend: false, yaxis: { title: 'US$ bi', zeroline: true }, margin: { l: 8, r: 12, t: 22, b: 8 } }));

  const gross = f.map((r) => (r.gross_profit_usd_b / r.revenue_usd_b) * 100);
  const net = f.map((r) => (r.net_income_usd_b / r.revenue_usd_b) * 100);
  plot('chart-margins', [
    {
      type: 'scatter', mode: 'lines+markers', x, y: gross, name: 'Margem bruta',
      line: { color: c.NU, width: 2.5 }, marker: { size: 9 }, hovertemplate: 'Bruta: %{y:.1f}%<extra></extra>',
    },
    {
      type: 'scatter', mode: 'lines+markers', x, y: net, name: 'Margem líquida',
      line: { color: c.nuDeep, width: 2.5, dash: 'dash' }, marker: { size: 9, symbol: 'diamond' }, hovertemplate: 'Líquida: %{y:.1f}%<extra></extra>',
    },
  ], layout({ hovermode: 'x unified', yaxis: { title: '% da receita', ticksuffix: '%', zeroline: true } }));

  const firstPositive = f.find((r) => r.net_income_usd_b > 0);
  const latest = f[f.length - 1];
  $('profit-insight').innerHTML = firstPositive
    ? `<strong>Ponto de inflexão:</strong> o lucro líquido IFRS fica positivo em <b>${firstPositive.year}</b> e chega a <b>${usdB(latest.net_income_usd_b)}</b> em ${latest.year}, com margem líquida de <b>${pct(net[net.length - 1])}</b>.`
    : '<strong>Leitura:</strong> a série ainda não apresenta lucro líquido positivo.';
}

// ---------- Risco ----------
function renderRisk() {
  const c = C();
  const d = state.data;
  const risk = d.risk.filter((r) => r.period);
  setText('risk-source', `Fonte: ${d.meta.risk_source || 'Pilar 3'}`);
  const x = risk.map((r) => r.period);
  const dateAxis = { type: 'date', tickformat: '%Y' };

  plot('chart-capital', [
    {
      type: 'scatter', mode: 'lines+markers', x, y: values(risk, 'rwa_total_brl_b'), name: 'RWA total',
      connectgaps: true, line: { color: c.nuSoft, width: 2.5 }, marker: { size: 6 },
      hovertemplate: 'RWA: R$ %{y:.1f} bi<extra></extra>',
    },
    {
      type: 'scatter', mode: 'lines+markers', x, y: values(risk, 'capital_principal_brl_b'), name: 'Capital Principal',
      connectgaps: true, line: { color: c.NU, width: 2.5 }, marker: { size: 6 },
      hovertemplate: 'Capital Principal: R$ %{y:.1f} bi<extra></extra>',
    },
  ], layout({ hovermode: 'x unified', xaxis: { ...dateAxis, hoverformat: '%m/%Y' }, yaxis: { title: 'R$ bi' } }));

  plot('chart-prudential', [
    {
      type: 'scatter', mode: 'lines+markers', x, y: values(risk, 'basel_index_pct'), name: 'Índice de Basileia',
      connectgaps: true, line: { color: c.NU, width: 2.5 }, marker: { size: 6 },
      hovertemplate: 'Basileia: %{y:.2f}%<extra></extra>',
    },
    {
      type: 'scatter', mode: 'lines+markers', x, y: values(risk, 'icp_pct'), name: 'ICP',
      connectgaps: true, line: { color: c.nuDeep, width: 2, dash: 'dash' }, marker: { size: 6, symbol: 'diamond' },
      hovertemplate: 'ICP: %{y:.2f}%<extra></extra>',
    },
  ], layout({
    hovermode: 'x unified',
    xaxis: { ...dateAxis, hoverformat: '%m/%Y' },
    yaxis: { title: '%', ticksuffix: '%', rangemode: 'tozero' },
    shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 10.5, y1: 10.5, line: { color: c.negative, width: 1, dash: 'dot' } }],
    annotations: [{ xref: 'paper', x: 0.01, y: 10.5, xanchor: 'left', yanchor: 'top', yshift: -2, showarrow: false, text: 'Basileia mínimo + ACP · 10,5%', font: { size: 10, color: c.muted } }],
  }));

  const det = d.risk_2025 || [];
  plot('chart-credit-risk', [{
    type: 'bar', x: values(det, 'quarter'), y: values(det, 'rwa_credito_brl_b'), marker: { color: c.NU },
    text: values(det, 'rwa_credito_brl_b').map((v) => fmt1.format(v)), textposition: 'outside', cliponaxis: false, textfont: { color: c.ink },
    hovertemplate: '%{x}: R$ %{y:.1f} bi<extra></extra>',
  }], layout({ showlegend: false, yaxis: { title: 'R$ bi' }, margin: { l: 8, r: 12, t: 22, b: 8 } }));

  plot('chart-market-risk', [
    {
      type: 'bar', x: values(det, 'quarter'), y: values(det, 'rwa_cambio_brl_m'), name: 'Câmbio', marker: { color: c.NU },
      text: values(det, 'rwa_cambio_brl_m').map((v) => fmt0.format(v)), textposition: 'outside', cliponaxis: false, textfont: { color: c.ink },
      hovertemplate: 'Câmbio: R$ %{y:,.1f} mi<extra></extra>',
    },
    {
      type: 'bar', x: values(det, 'quarter'), y: values(det, 'rwa_juros_brl_m'), name: 'Juros', marker: { color: c.nuSoft },
      text: values(det, 'rwa_juros_brl_m').map((v) => fmt1.format(v)), textposition: 'outside', cliponaxis: false, textfont: { color: c.ink },
      hovertemplate: 'Juros: R$ %{y:,.1f} mi<extra></extra>',
    },
  ], layout({ barmode: 'group', hovermode: 'x unified', yaxis: { title: 'R$ mi' }, margin: { l: 8, r: 12, t: 30, b: 8 } }));

  if (det.length >= 2) {
    const a = det[det.length - 1];
    const b = det[det.length - 2];
    $('risk-insight').innerHTML = `<strong>Sinal para investigar:</strong> o RWA cambial de ${a.quarter}/2025 é <b>${fmt1.format(a.rwa_cambio_brl_m / b.rwa_cambio_brl_m)}×</b> o de ${b.quarter}. A mudança é destacada, mas sem atribuir causa sem respaldo das notas regulatórias.`;
  }
}

// ---------- Clientes ----------
function renderCustomer() {
  const c = C();
  const cu = state.data.customer;
  setText('customer-total', fmt0.format(cu.total));
  setText('customer-loss', cu.loss_share_pct == null ? '—' : pct(cu.loss_share_pct));
  setText('customer-security', cu.security_signals == null ? '—' : fmt0.format(cu.security_signals));
  setText('customer-source', cu.source_label || '');

  const cats = [...cu.categories].sort((a, b) => a.reclamacoes - b.reclamacoes);
  plot('chart-categories', [{
    type: 'bar', orientation: 'h', x: values(cats, 'reclamacoes'), y: values(cats, 'categoria'),
    marker: { color: c.NU }, text: values(cats, 'reclamacoes'), textposition: 'outside', cliponaxis: false, textfont: { color: c.ink },
    hovertemplate: '%{y}: %{x} reclamações<extra></extra>',
  }], layout({ showlegend: false, bargap: 0.28, xaxis: { showgrid: true, title: 'Reclamações' }, yaxis: { showgrid: false }, margin: { l: 8, r: 30, t: 8, b: 8 } }));

  const sevOrder = ['Alta', 'Média', 'Baixa'];
  const sev = [...cu.severity].sort((a, b) => sevOrder.indexOf(a.severidade) - sevOrder.indexOf(b.severidade));
  const sevColor = { Alta: c.negative, 'Média': '#D97706', Baixa: c.neutral };
  const total = sev.reduce((a, r) => a + r.reclamacoes, 0) || 1;
  const sevRev = [...sev].reverse();
  plot('chart-severity', [{
    type: 'bar', orientation: 'h', y: values(sevRev, 'severidade'), x: values(sevRev, 'reclamacoes'),
    marker: { color: sevRev.map((r) => sevColor[r.severidade] || c.nuSoft) },
    text: sevRev.map((r) => `${r.reclamacoes} · ${fmt0.format((r.reclamacoes / total) * 100)}%`),
    textposition: 'outside', cliponaxis: false, textfont: { color: c.ink },
    hovertemplate: '%{y}: %{x} reclamações<extra></extra>',
  }], layout({ showlegend: false, bargap: 0.3, xaxis: { visible: false }, yaxis: { showgrid: false }, margin: { l: 8, r: 70, t: 4, b: 4 } }));

  plot('chart-clusters', [{
    type: 'bar', x: values(cu.clusters, 'cluster').map((v) => `Cluster ${v}`), y: values(cu.clusters, 'reclamacoes'),
    marker: { color: c.nuSoft }, text: values(cu.clusters, 'reclamacoes'), textposition: 'outside', cliponaxis: false, textfont: { color: c.ink },
    hovertemplate: '%{x}: %{y} reclamações<extra></extra>',
  }], layout({ showlegend: false, yaxis: { visible: false }, margin: { l: 8, r: 8, t: 22, b: 8 } }));
}

// ---------- Fontes ----------
function renderSources() {
  $('source-table').innerHTML = state.data.sources.map((r) => `
    <tr>
      <td><strong>${escapeHtml(r.dataset)}</strong></td>
      <td>${escapeHtml(r.period)}</td>
      <td>${escapeHtml(r.source_type)}</td>
      <td>${escapeHtml(r.source)}</td>
    </tr>`).join('');
}

// ---------- Abas ----------
const RENDERERS = {
  mercado: renderMarket,
  crescimento: renderGrowth,
  rentabilidade: renderProfitability,
  risco: renderRisk,
  clientes: renderCustomer,
  metodologia: renderSources,
};

function showTab(name, { focus = false, push = true } = {}) {
  if (!RENDERERS[name]) name = 'mercado';
  state.tab = name;
  document.querySelectorAll('.tab').forEach((t) => {
    const on = t.dataset.tab === name;
    t.setAttribute('aria-selected', String(on));
    t.tabIndex = on ? 0 : -1;
    if (on && focus) t.focus();
    if (on) t.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  });
  document.querySelectorAll('.panel-view').forEach((p) => { p.hidden = p.id !== name; });
  if (push && location.hash !== `#${name}`) history.replaceState(null, '', `#${name}`);
  if (state.data) {
    RENDERERS[name]();
    state.rendered.add(name);
  }
}

function setupTabs() {
  const tabs = [...document.querySelectorAll('.tab')];
  tabs.forEach((t) => t.addEventListener('click', () => showTab(t.dataset.tab)));
  document.querySelector('.tabbar').addEventListener('keydown', (e) => {
    const i = tabs.findIndex((t) => t.dataset.tab === state.tab);
    let j = null;
    if (e.key === 'ArrowRight') j = (i + 1) % tabs.length;
    if (e.key === 'ArrowLeft') j = (i - 1 + tabs.length) % tabs.length;
    if (e.key === 'Home') j = 0;
    if (e.key === 'End') j = tabs.length - 1;
    if (j != null) { e.preventDefault(); showTab(tabs[j].dataset.tab, { focus: true }); }
  });
  window.addEventListener('hashchange', () => showTab(location.hash.slice(1), { push: false }));
}

function rerenderAll() {
  if (!state.data) return;
  renderHeader(state.data);
  RENDERERS[state.tab]();
  state.rendered = new Set([state.tab]);
}

// ---------- Inicialização ----------
async function init() {
  setupThemeToggle();
  setupTabs();
  showTab(location.hash.slice(1) || 'mercado', { push: false });
  try {
    const res = await fetch('data/dashboard-data.json', { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.data = await res.json();
    renderHeader(state.data);
    setupMarketControls();
    showTab(state.tab, { push: false });
  } catch (err) {
    console.error('Falha ao carregar o dashboard:', err);
    $('load-error').hidden = false;
  }
}

document.addEventListener('DOMContentLoaded', init);
