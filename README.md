# Nubank-2.0

> 📊 **Acesse o dashboard:** [thaisnakazone.github.io/Nubank-2.0](https://thaisnakazone.github.io/Nubank-2.0/)  
> Atualizado automaticamente todo dia útil com dados da Twelve Data e do Banco Central.

Projeto Integrador 4 – Fatec Sebrae (2026)  

Este repositório é uma continuação e aprimoramento do projeto [Nubank Financial Analysis](https://github.com/pfutagawa/nubank-financial-analysis-ds).

## 🚀 Objetivo
Automatizar a coleta e análise de dados financeiros do Nubank, aplicando conceitos de **Big Data, NoSQL e Data Visualization** aprendidos no semestre.

## 🔑 Principais melhorias
- **Substituição da ingestão de dados via arquivos CSV/XLSX** por integração direta com a **API Twelve Data** (ativos `NU`, `ITUB` e `BBD`).  
- **Armazenamento automatizado em MongoDB Atlas**, garantindo idempotência com upserts (`UpdateOne`), índice único composto em `(ticker, datetime)` e atualização contínua dos dados.  
- **Dashboard interativo atualizado periodicamente** via GitHub Actions (agendamento cron de seg a sex às 22h UTC), eliminando a necessidade de manipulação manual de planilhas.  
- **Estrutura modular e colaborativa** pensada para trabalho em equipe com branches e pull requests.

## 🛠️ Tecnologias utilizadas
- Python 3.12 (pandas, requests, streamlit, plotly)  
- MongoDB Atlas (NoSQL - PyMongo)  
- API Twelve Data (cotações financeiras OHLCV)  
- GitHub Actions (CI/CD, agendamento diário e deploy)  
- GitHub Pages / Firebase Hosting (publicação estática do dashboard)  

## 📂 Estrutura do projeto   
```text
Nubank-2.0/
│
├── data_ingestion/        # Módulo de integração e validação com Twelve Data API
│   ├── client.py          # Cliente HTTP com rate-limiting e sanitização
│   ├── validator.py       # Validador de dados OHLCV
│   ├── sanitizer.py       # Proteção contra vazamento de credenciais em logs
│   └── service.py         # Orquestrador do fluxo de coleta
│
├── database/              # Conexão e operações com MongoDB Atlas
│   ├── connection.py      # Gerenciamento de conexão com Atlas e ping
│   ├── operations.py      # Operações de upsert, índices únicos e consultas
│   └── seed_mongodb.py    # Carga das séries fundamentalistas no Atlas
│
├── dashboard/             # Código do dashboard interativo em Python
│   └── app.py             # Aplicação Streamlit conectada diretamente ao MongoDB
│
├── docs/                  # Dashboard web estático publicado no GitHub Pages
│   ├── index.html         # Página principal com gráficos Plotly.js
│   ├── css/style.css      # Estilização moderna Nubank
│   ├── js/dashboard.js    # Lógica interativa de visualização
│   └── data/              # Payload JSON atualizado automaticamente
│
├── scripts/               # Utilitários de manutenção e limpeza controlada
├── tests/                 # Suíte de testes unitários automatizados
├── ingestao.py            # Ponto de entrada CLI para ingestão
├── consultar.py           # Utilitário CLI para verificação do banco
└── README.md              # Documentação do projeto
```

## ⚙️ Como configurar e executar

### 1. Pré-requisitos
- Python 3.12 instalado
- Conta no [Twelve Data](https://twelvedata.com/) para obter a chave gratuita de API
- Cluster configurado no [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)

### 2. Configuração do ambiente
Clone o repositório e crie o ambiente virtual:
```bash
git clone https://github.com/thaisnakazone/Nubank-2.0.git
cd Nubank-2.0
python -m venv venv
venv\Scripts\activate   # No Windows (ou source venv/bin/activate no Linux/macOS)
pip install -r requirements.txt
```

Crie o arquivo `.env` na raiz do projeto (baseado em `.env.example`):
```ini
TWELVE_DATA_API_KEY=sua_chave_twelve_data_aqui
MONGO_URI=mongodb+srv://usuario:senha@cluster0.exemplo.mongodb.net/?appName=Cluster0
```

### 3. Coleta e Ingestão de Dados
Para executar a coleta direta da API Twelve Data e persistir no MongoDB Atlas:
```bash
python ingestao.py
```

Para inspecionar o status e dados no MongoDB Atlas:
```bash
python consultar.py
```

### 4. Executando o Dashboard Interativo Local
Inicie o dashboard interativo construído em Streamlit:
```bash
streamlit run dashboard/app.py
# ou alternativamente:
streamlit run app.py
```

O dashboard conectará diretamente ao MongoDB Atlas e exibirá as cotações em tempo real/diárias, médias móveis, volume e comparativo de mercado, além das séries históricas de crescimento, rentabilidade e risco.

### 5. Atualização Periódica e Automatizada (Sem manipulação manual)
O repositório conta com GitHub Actions configurado em `.github/workflows/coleta_diaria.yml`:
- **Disparo periódico:** Executa de segunda a sexta-feira às 22:00 UTC (após o fechamento dos mercados).
- **Ingestão automática:** Coleta os dados da Twelve Data e atualiza o MongoDB Atlas via `ingestao.py`.
- **Publicação contínua:** Reconstrói o payload `docs/data/dashboard-data.json` e dispara o deploy no GitHub Pages.
- **Zero manipulação manual de arquivos:** Todo o fluxo ocorre na nuvem de forma transparente e auditável.

### 5.1 Publicação no GitHub Pages
O dashboard público é o site estático da pasta `docs/` (HTML + CSS + Plotly.js), que lê `docs/data/dashboard-data.json`.

1. No GitHub, abra **Settings → Pages** e, em **Build and deployment → Source**, escolha **GitHub Actions**.
2. Em **Settings → Secrets and variables → Actions**, cadastre `MONGO_URI` e `TWELVE_DATA_API_KEY`.
3. Faça push na branch `main` (ou rode o workflow **Build and deploy GitHub Pages** manualmente na aba *Actions*).
4. O site fica disponível em `https://thaisnakazone.github.io/Nubank-2.0/`.

Após cada coleta diária, o workflow de deploy é disparado automaticamente (`workflow_run`), então o site sempre reflete os dados mais recentes do MongoDB Atlas.

Para visualizar localmente:
```bash
python -m src.build_web_data      # gera docs/data/dashboard-data.json
python -m http.server -d docs     # abra http://localhost:8000
```

### 5.2 Reclamações no Banco Central (100% automático)
O workflow **Reclamações BCB** (`.github/workflows/reclamacoes_bcb.yml`) roda toda segunda-feira e coleta, para Nubank, Itaú e Bradesco:
- **Ranking trimestral** via API oficial do BCB: índice de reclamações, reclamações procedentes e clientes;
- **Irregularidades por instituição**: o script navega pela página de histórico do ranking e baixa o CSV de cada trimestre (esse detalhamento não está na API).

As irregularidades são agrupadas em temas (Segurança e fraude, Pix, Cartão de crédito, Crédito, Tarifas, Atendimento, Conta, Cadastros) e gravadas no MongoDB Atlas (`ranking_reclamacoes_bcb` e `irregularidades_bcb`) e em `data/processed/bcb_*.csv`. A coleta é incremental: só busca trimestres novos e atualiza o mais recente.

```bash
python -m src.ingest_bcb_ranking              # coleta incremental
python -m src.ingest_bcb_ranking --completo   # recoleta tudo desde 2021
```

> Metodologia: a partir do 2º trimestre de 2024 o BCB passou a calcular o índice com reclamações procedentes **extrapoladas** a partir de uma amostra, o que eleva o patamar da série. O dashboard marca essa quebra no gráfico.

### 6. Execução de Testes
Para rodar a suíte de testes unitários:
```bash
python -m unittest discover tests
```

---

📌 **Nota:** Este projeto é acadêmico e não possui vínculo oficial com o Nubank.  