# Intermediário do chat "Pergunte à IA" (Cloudflare Worker)

O dashboard é um site estático, e a chave da IA não pode ficar no navegador. Este Worker fica no meio do caminho: recebe a pergunta, aplica os limites, chama o Claude com os números do dashboard e registra o uso num banco D1. O plano gratuito da Cloudflare cobre o uso deste projeto.

| Rota | O que faz |
|---|---|
| `POST /chat` | pergunta livre, respondida pela IA (teto de 30 por dia, 6 por minuto, 300 caracteres) |
| `POST /log` | registra o clique numa pergunta pronta (não usa IA) |
| `GET /stats` | totais de uso, sem textos de perguntas livres |
| `GET /export` | registros completos, só com a senha `EXPORT_TOKEN` (usada pela coleta diária) |

Nenhum IP ou dado de identificação é gravado.

## Publicar pelo painel da Cloudflare (sem instalar nada)

Os nomes dos menus podem mudar um pouco com o tempo.

1. Crie uma conta gratuita em https://dash.cloudflare.com.
2. **Banco de dados:** em *Storage & Databases › D1 SQL Database*, crie um banco chamado `nubank-chat`. Não precisa criar tabelas: o Worker cria sozinho.
3. **Worker:** em *Workers & Pages › Create › Worker* (modelo "Hello World"), dê o nome `nubank-chat` e publique. Depois clique em *Edit code*, apague tudo, cole o conteúdo de [`src/worker.js`](src/worker.js) e clique em *Deploy*.
4. **Ligar o banco:** no Worker, em *Settings › Bindings › Add › D1 database*, use o nome de variável `DB` e escolha o banco `nubank-chat`.
5. **Segredos:** em *Settings › Variables and Secrets*, adicione dois itens do tipo **Secret**:
   - `ANTHROPIC_API_KEY`: a chave da Anthropic. De preferência, crie no Console uma chave só para o chat, para poder desligá-la sem afetar o parecer diário.
   - `EXPORT_TOKEN`: uma senha longa inventada por você (20 caracteres ou mais).
6. **Testar:** abra `https://nubank-chat.SEU-USUARIO.workers.dev/stats` no navegador. Deve aparecer um JSON com os totais zerados.
7. **Ligar no site:** coloque o endereço do Worker (sem barra no final) em `docs/js/chat-config.js` e faça o push.
8. **Cópia para o MongoDB:** no GitHub, crie o secret `CHAT_EXPORT_TOKEN` com a mesma senha do `EXPORT_TOKEN`.

No Console da Anthropic, confira em *Settings › Billing* se a recarga automática está desligada. Assim o gasto máximo é o saldo pré-pago.

## Publicar pelo terminal (alternativa)

```bash
cd chat-worker
npx wrangler login
npx wrangler d1 create nubank-chat        # copie o database_id para o wrangler.toml
npx wrangler deploy
npx wrangler secret put ANTHROPIC_API_KEY
npx wrangler secret put EXPORT_TOKEN
```

## Ajustes

Os limites têm valores padrão no código e podem ser trocados em *Settings › Variables and Secrets* (tipo Text): `LIMITE_DIARIO` (30), `LIMITE_POR_MINUTO` (6), `LIMITE_CLIQUES_DIA` (500), `MODEL`, `ALLOWED_ORIGIN` e `CONTEXT_URL`.

Para desligar o chat livre na hora, apague o endereço em `docs/js/chat-config.js` ou remova o secret `ANTHROPIC_API_KEY` do Worker. As perguntas prontas continuam funcionando.

## Testes

```bash
npm install
npm test
```

Os testes rodam o Worker de verdade num simulador local (Miniflare), com o banco D1 simulado e a IA simulada. Eles cobrem resposta normal, pergunta fora do tema, bloqueio de recomendação de compra e venda, teto diário, limite por minuto, registro de cliques e exportação protegida.
