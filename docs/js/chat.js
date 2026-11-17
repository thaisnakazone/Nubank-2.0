/* Nubank em Dados 2.0 — "Pergunte à IA"
   - Perguntas prontas: respostas geradas pela IA uma vez por dia (vêm no dashboard-data.json); clicar não gasta IA.
   - Pergunta livre: vai para o intermediário (window.NU_CHAT_API), que guarda a chave, aplica o teto diário e registra o uso. */
(() => {
  const API = String(window.NU_CHAT_API || '').replace(/\/+$/, '');
  const MAX = 300;
  const el = (id) => document.getElementById(id);
  const brl = new Intl.NumberFormat('pt-BR');
  let enviando = false;
  let restantes = null;

  function bolha(quem, texto, extra = '') {
    const log = el('chat-log');
    const item = document.createElement('div');
    item.className = `chat-msg chat-${quem}${extra ? ` ${extra}` : ''}`;
    const rotulo = document.createElement('span');
    rotulo.className = 'chat-who';
    rotulo.textContent = quem === 'user' ? 'Você' : 'IA';
    const corpo = document.createElement('p');
    corpo.textContent = texto;
    item.append(rotulo, corpo);
    log.append(item);
    log.hidden = false;
    log.scrollTop = log.scrollHeight;
    return corpo;
  }

  function atualizarRestantes(n, limite) {
    if (typeof n !== 'number') return;
    restantes = n;
    const meta = el('chat-meta');
    meta.textContent = n > 0
      ? `Perguntas livres disponíveis hoje: ${n}${limite ? ` de ${limite}` : ''}`
      : 'Limite diário de perguntas livres atingido. As perguntas prontas continuam disponíveis.';
    el('chat-input').disabled = n <= 0;
    el('chat-send').disabled = n <= 0;
  }

  function registrarClique(item) {
    if (!API) return;
    fetch(`${API}/log`, {
      method: 'POST', keepalive: true, headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: item.id, texto: item.pergunta }),
    }).catch(() => {});
  }

  function montarProntas(faq) {
    const box = el('chat-chips');
    box.replaceChildren();
    (faq.itens || []).forEach((item) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'chat-chip';
      b.textContent = item.pergunta;
      b.addEventListener('click', () => {
        bolha('user', item.pergunta);
        bolha('ai', item.resposta);
        registrarClique(item);
      });
      box.append(b);
    });
    el('chat-prontas').hidden = !box.children.length;
    const mais = el('chat-more');
    mais.addEventListener('click', () => {
      const aberto = box.classList.toggle('aberto');
      mais.setAttribute('aria-expanded', String(aberto));
      mais.textContent = aberto ? 'Menos perguntas' : 'Mais perguntas';
    });
  }

  async function perguntar(texto) {
    if (enviando) return;
    enviando = true;
    el('chat-send').disabled = true;
    bolha('user', texto);
    const corpo = bolha('ai', 'Consultando os dados…', 'chat-wait');
    try {
      const resp = await fetch(`${API}/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pergunta: texto }) });
      const j = await resp.json().catch(() => ({}));
      corpo.textContent = j.resposta || j.mensagem || 'Não consegui responder agora. Tente de novo em instantes.';
      if (typeof j.restantes_hoje === 'number') atualizarRestantes(j.restantes_hoje, j.limite);
    } catch (e) {
      corpo.textContent = 'Não consegui falar com o serviço do chat. Tente de novo em instantes ou use as perguntas prontas.';
    } finally {
      corpo.parentElement.classList.remove('chat-wait');
      enviando = false;
      if (restantes === null || restantes > 0) el('chat-send').disabled = false;
      el('chat-log').scrollTop = el('chat-log').scrollHeight;
    }
  }

  function montarLivre() {
    const form = el('chat-form');
    const input = el('chat-input');
    form.hidden = false;
    input.maxLength = MAX;
    input.addEventListener('input', () => { el('chat-count').textContent = `${input.value.length}/${MAX}`; });
    form.addEventListener('submit', (ev) => {
      ev.preventDefault();
      const texto = input.value.replace(/\s+/g, ' ').trim();
      if (texto.length < 3) { input.focus(); return; }
      input.value = '';
      el('chat-count').textContent = `0/${MAX}`;
      perguntar(texto);
    });
  }

  function stat(rotulo, valor, detalhe) {
    const d = document.createElement('div');
    d.className = 'stat';
    const a = document.createElement('span'); a.className = 'stat-label'; a.textContent = rotulo;
    const b = document.createElement('strong'); b.className = 'stat-value'; b.textContent = valor;
    const c = document.createElement('small'); c.textContent = detalhe;
    d.append(a, b, c);
    return d;
  }

  async function carregarUso() {
    if (!API) return;
    try {
      const s = await fetch(`${API}/stats`).then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.status))));
      atualizarRestantes(s.hoje.restantes, s.hoje.limite);
      const usd = (v) => `US$ ${Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 4, maximumFractionDigits: 4 })}`;
      el('chat-usage-stats').replaceChildren(
        stat('Perguntas livres hoje', `${brl.format(s.hoje.livres)} de ${brl.format(s.hoje.limite)}`, 'respondidas pela IA'),
        stat('Perguntas prontas hoje', brl.format(s.hoje.botoes), 'cliques, sem custo de IA'),
        stat('No mês', brl.format(s.mes.livres + s.mes.botoes), `${brl.format(s.mes.livres)} livres · ${brl.format(s.mes.botoes)} prontas`),
        stat('Custo estimado no mês', usd(s.mes.custo_usd), `total acumulado: ${usd(s.total.custo_usd)}`),
      );
      const top = el('chat-usage-top');
      top.replaceChildren();
      (s.top_perguntas_prontas || []).forEach((t) => {
        const li = document.createElement('li');
        li.textContent = `${t.texto} · ${brl.format(t.vezes)} ${t.vezes === 1 ? 'vez' : 'vezes'}`;
        top.append(li);
      });
      el('chat-usage-top-wrap').hidden = !top.children.length;
      el('chat-usage').hidden = false;
    } catch (e) { /* sem estatísticas: o chat segue funcionando */ }
  }

  document.addEventListener('nu:data', (ev) => {
    const faq = (ev.detail && ev.detail.chat_faq) || null;
    const temProntas = !!(faq && faq.itens && faq.itens.length);
    if (!temProntas && !API) return;
    if (temProntas) montarProntas(faq);
    if (API) { montarLivre(); carregarUso(); }
    el('chat-aviso').textContent = `${(faq && faq.aviso) || 'Respostas geradas por IA a partir dos dados do dashboard, para fins educacionais. Não é recomendação de investimento.'}${API ? ' As perguntas são registradas de forma anônima para fins acadêmicos.' : ''}`;
    el('chat-panel').hidden = false;
  });
})();
