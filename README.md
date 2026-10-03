# Nubank-2.0

Projeto Integrador 4 – Fatec Sebrae (2026)  

Este repositório é uma continuação e aprimoramento do projeto [Nubank Financial Analysis](https://github.com/pfutagawa/nubank-financial-analysis-ds).

## 🚀 Objetivo
Automatizar a coleta e análise de dados financeiros do Nubank, aplicando conceitos de **Big Data, NoSQL e Data Visualization** aprendidos no semestre.

## 🔑 Principais melhorias
- Substituição da ingestão de dados via arquivos CSV/XLSX por integração direta com a **API Twelve**.  
- Armazenamento automatizado em **MongoDB Atlas**, permitindo atualização contínua dos dados.  
- Dashboard interativo atualizado periodicamente sem necessidade de manipulação manual de arquivos.  
- Estrutura pensada para colaboração em grupo com branches e pull requests.  

## 🛠️ Tecnologias utilizadas
- Python (pandas, requests, plotly/dash)  
- MongoDB Atlas (NoSQL)  
- GitHub Pages / Firebase Hosting (publicação)  
- API Twelve (dados financeiros)  

## 📂 Estrutura do projeto   
```text
Nubank-2.0/
│
├── data_ingestion/        # Scripts para coletar dados da API
├── database/              # Conexão e operações com MongoDB
├── dashboard/             # Código do dashboard interativo
├── docs/                  # Documentação e relatórios
└── README.md              # Este arquivo

## 👥 Colaboração
- Cada integrante deve criar **branches** para suas alterações (ex.: `feature/api-ingestao`, `feature/mongodb`).
- As mudanças entram via **Pull Request**, mantendo o histórico organizado.
- Usuários e permissões são gerenciados no **MongoDB Atlas** para acesso compartilhado ao banco.

---

📌 **Nota:** Este projeto é acadêmico e não possui vínculo oficial com o Nubank.  