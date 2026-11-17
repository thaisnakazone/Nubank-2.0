// Testes locais do intermediário do chat (Miniflare simula o Worker e o banco D1; a IA é simulada).
// Rodar:  npm install && npm test
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { Miniflare, Response as MfResponse } from 'miniflare';

const ORIGEM = 'https://thaisnakazone.github.io';
const TOKEN = 'token-de-teste-bem-comprido-123';
let chamadasIA = 0;

function iaSimulada(request) {
  const url = new URL(request.url);
  if (url.hostname === 'thaisnakazone.github.io') {
    return new MfResponse(JSON.stringify({ indicadores: { rentabilidade: { lucro_liquido_usd_bi: 2.87 } } }), { headers: { 'content-type': 'application/json' } });
  }
  if (url.hostname === 'api.anthropic.com') {
    return request.json().then((body) => {
      chamadasIA += 1;
      assert.equal(request.headers.get('x-api-key'), 'chave-falsa');
      const pergunta = body.messages[0].content;
      let saida = { no_tema: true, resposta: 'Sim. Em 2025 o lucro foi de US$ 2,87 bilhões.' };
      if (pergunta.includes('bolo')) saida = { no_tema: false, resposta: '' };
      if (pergunta.includes('devo comprar')) saida = { no_tema: true, resposta: 'Compre ações do Nubank agora.' };
      if (pergunta.includes('quebra')) return new MfResponse('{"error":{"type":"overloaded_error"}}', { status: 529 });
      return new MfResponse(JSON.stringify({ content: [{ type: 'text', text: JSON.stringify(saida) }], usage: { input_tokens: 2000, output_tokens: 100 } }), { headers: { 'content-type': 'application/json' } });
    });
  }
  return new MfResponse('bloqueado', { status: 500 });
}

const novo = (extra = {}) => new Miniflare({
  modules: true,
  scriptPath: new URL('../src/worker.js', import.meta.url).pathname,
  compatibilityDate: '2026-01-01',
  d1Databases: { DB: 'teste' },
  bindings: { ANTHROPIC_API_KEY: 'chave-falsa', EXPORT_TOKEN: TOKEN, LIMITE_DIARIO: '4', ...extra },
  outboundService: iaSimulada,
});

let mf;
before(() => { mf = novo(); });
after(async () => { await mf.dispose(); });

const post = (m, rota, corpo, origem = ORIGEM) => m.dispatchFetch(`http://chat.local${rota}`, {
  method: 'POST', headers: { 'content-type': 'application/json', ...(origem ? { Origin: origem } : {}) }, body: JSON.stringify(corpo),
});
const get = (m, rota, headers = {}) => m.dispatchFetch(`http://chat.local${rota}`, { headers });

test('estatísticas começam zeradas', async () => {
  const s = await (await get(mf, '/stats')).json();
  assert.equal(s.hoje.livres, 0);
  assert.equal(s.hoje.limite, 4);
  assert.equal(s.hoje.restantes, 4);
});

test('recusa origem desconhecida e perguntas inválidas', async () => {
  assert.equal((await post(mf, '/chat', { pergunta: 'O Nubank teve lucro?' }, 'https://outro.site')).status, 403);
  assert.equal((await post(mf, '/chat', { pergunta: 'O Nubank teve lucro?' }, null)).status, 403);
  assert.equal((await post(mf, '/chat', { pergunta: 'a' })).status, 400);
  assert.equal((await post(mf, '/chat', { pergunta: 'x'.repeat(301) })).status, 400);
  assert.equal(chamadasIA, 0);
});

test('responde, registra tokens e custo', async () => {
  const r = await post(mf, '/chat', { pergunta: 'O Nubank teve lucro em 2025?' });
  assert.equal(r.status, 200);
  assert.equal(r.headers.get('access-control-allow-origin'), ORIGEM);
  const j = await r.json();
  assert.equal(j.situacao, 'respondida');
  assert.match(j.resposta, /2,87/);
  assert.equal(j.restantes_hoje, 3);
  const s = await (await get(mf, '/stats')).json();
  assert.equal(s.hoje.livres, 1);
  assert.equal(s.hoje.tokens_entrada, 2000);
  assert.equal(s.hoje.custo_usd, 0.00025); // 2000 × 0,10/1M + 100 × 0,50/1M
});

test('fora do tema e recomendação de compra são trocadas por mensagens fixas', async () => {
  const fora = await (await post(mf, '/chat', { pergunta: 'Como faço um bolo de cenoura?' })).json();
  assert.equal(fora.situacao, 'fora_do_tema');
  assert.match(fora.resposta, /Só consigo responder/);
  const filtrada = await (await post(mf, '/chat', { pergunta: 'devo comprar a ação?' })).json();
  assert.equal(filtrada.situacao, 'filtrada');
  assert.doesNotMatch(filtrada.resposta, /Compre/);
});

test('erro da IA não conta no limite e devolve mensagem amigável', async () => {
  const r = await post(mf, '/chat', { pergunta: 'isso quebra a IA?' });
  assert.equal(r.status, 502);
  const s = await (await get(mf, '/stats')).json();
  assert.equal(s.hoje.livres, 3);
});

test('teto diário bloqueia sem chamar a IA', async () => {
  assert.equal((await post(mf, '/chat', { pergunta: 'O capital é suficiente?' })).status, 200);
  const antes = chamadasIA;
  const r = await post(mf, '/chat', { pergunta: 'E a ação, como está?' });
  assert.equal(r.status, 429);
  assert.equal((await r.json()).erro, 'limite_diario');
  assert.equal(chamadasIA, antes);
});

test('cliques em perguntas prontas são registrados sem IA', async () => {
  const antes = chamadasIA;
  for (let i = 0; i < 2; i += 1) assert.equal((await post(mf, '/log', { id: 'esta_bem', texto: 'O Nubank está bem?' })).status, 200);
  const s = await (await get(mf, '/stats')).json();
  assert.equal(s.hoje.botoes, 2);
  assert.deepEqual(s.top_perguntas_prontas[0], { texto: 'O Nubank está bem?', vezes: 2 });
  assert.equal(chamadasIA, antes);
});

test('exportação exige o token e traz os registros sem IP', async () => {
  assert.equal((await get(mf, '/export')).status, 401);
  assert.equal((await get(mf, '/export', { Authorization: 'Bearer errado' })).status, 401);
  const j = await (await get(mf, '/export?desde_id=0', { Authorization: `Bearer ${TOKEN}` })).json();
  assert.ok(j.registros.length >= 7);
  const campos = Object.keys(j.registros[0]).sort();
  assert.deepEqual(campos, ['criado_em', 'custo_usd', 'dia_brt', 'id', 'modelo', 'pergunta_id', 'resposta', 'situacao', 'texto', 'tipo', 'tokens_entrada', 'tokens_saida']);
  assert.ok(j.registros.some((r) => r.situacao === 'bloqueada_limite'));
  const parcial = await (await get(mf, `/export?desde_id=${j.registros.at(-1).id}`, { Authorization: `Bearer ${TOKEN}` })).json();
  assert.equal(parcial.registros.length, 0);
});

test('limite por minuto', async () => {
  const m = novo({ LIMITE_DIARIO: '50', LIMITE_POR_MINUTO: '2' });
  try {
    assert.equal((await post(m, '/chat', { pergunta: 'Pergunta um sobre lucro?' })).status, 200);
    assert.equal((await post(m, '/chat', { pergunta: 'Pergunta dois sobre lucro?' })).status, 200);
    const r = await post(m, '/chat', { pergunta: 'Pergunta três sobre lucro?' });
    assert.equal(r.status, 429);
    assert.equal((await r.json()).erro, 'ritmo');
  } finally { await m.dispose(); }
});
