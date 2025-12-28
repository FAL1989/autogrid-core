# AutoGrid - Prompt de Contexto do Projeto

## Visão Geral

O **AutoGrid** é uma plataforma open-source de trading automatizado de criptomoedas com estratégias Grid e DCA (Dollar Cost Averaging). O projeto foi estruturado para ser escalável, seguro e fácil de usar.

---

## Stack Tecnológica

### Backend (Python 3.11+)
- **FastAPI** - API REST assíncrona
- **Celery** - Processamento de tarefas em background
- **SQLAlchemy 2.0** - ORM assíncrono
- **CCXT** - Conexão com exchanges (Binance, MEXC, Bybit)
- **Pydantic v2** - Validação de dados

### Frontend (Node.js 20+)
- **Next.js 14** - React framework com App Router
- **TypeScript** - Tipagem estática
- **Tailwind CSS** - Estilização utility-first
- **Recharts** - Gráficos de performance
- **React Hook Form + Zod** - Formulários com validação

### Infraestrutura
- **PostgreSQL + TimescaleDB** - Banco de dados com séries temporais
- **Redis** - Cache e filas de mensagens
- **Docker Compose** - Orquestração de containers
- **GitHub Actions** - CI/CD

---

## Estrutura de Arquivos Criados

```
AutoGrid/
├── .claude/                          # Configuração Claude Code
│   ├── agents/                       # 10 agentes especializados
│   │   ├── trading-strategy.md       # Desenvolvimento de estratégias
│   │   ├── exchange-connector.md     # Integração com exchanges
│   │   ├── security-auditor.md       # Auditoria de segurança (opus)
│   │   ├── api-architect.md          # Design de API REST
│   │   ├── database.md               # Modelagem de dados
│   │   ├── frontend.md               # Desenvolvimento Next.js
│   │   ├── telegram-bot.md           # Bot de notificações
│   │   ├── backtesting-engine.md     # Engine de backtesting
│   │   ├── test-engineer.md          # Testes automatizados
│   │   └── devops.md                 # Infraestrutura Docker/CI
│   ├── skills/                       # 7 skills automáticas
│   │   ├── grid-configuration/       # Configurar bot Grid
│   │   ├── dca-configuration/        # Configurar bot DCA
│   │   ├── backtest-analysis/        # Analisar backtests
│   │   ├── exchange-setup/           # Configurar exchanges
│   │   ├── troubleshooting/          # Resolver problemas
│   │   ├── security-checklist/       # Verificar segurança
│   │   └── deployment/               # Deploy em produção
│   └── settings.json                 # Permissões e hooks
│
├── api/                              # Backend FastAPI
│   ├── __init__.py
│   ├── main.py                       # App FastAPI com rotas
│   ├── Dockerfile
│   ├── core/                         # ✅ NOVO - Core do sistema
│   │   ├── __init__.py
│   │   ├── config.py                 # Settings com pydantic-settings
│   │   ├── database.py               # Async SQLAlchemy session
│   │   ├── dependencies.py           # get_current_user dependency
│   │   └── rate_limiter.py           # Rate limiting com Redis
│   ├── routes/
│   │   ├── auth.py                   # Registro, login, refresh, /me
│   │   ├── bots.py                   # CRUD de bots + start/stop
│   │   └── backtest.py               # Executar backtests
│   ├── models/
│   │   ├── schemas.py                # Schemas Pydantic (User, Bot, Order)
│   │   └── orm.py                    # ✅ NOVO - SQLAlchemy ORM models
│   └── services/                     # ✅ NOVO - Serviços implementados
│       ├── __init__.py
│       ├── security.py               # Hash de senhas (bcrypt)
│       ├── jwt.py                    # Criação/validação JWT
│       └── user_service.py           # CRUD de usuários
│
├── bot/                              # Engine de Trading
│   ├── __init__.py
│   ├── engine.py                     # BotEngine com loop de execução
│   ├── Dockerfile
│   ├── strategies/
│   │   ├── base.py                   # BaseStrategy ABC + Order dataclass
│   │   ├── grid.py                   # GridStrategy completo
│   │   └── dca.py                    # DCAStrategy completo
│   └── exchange/
│       └── connector.py              # ExchangeConnector ABC + CCXTConnector
│
├── telegram/                         # Bot Telegram
│   ├── __init__.py
│   └── bot.py                        # TelegramBot com comandos e notificações
│
├── web/                              # Frontend Next.js
│   ├── app/
│   │   ├── layout.tsx                # Root layout com providers
│   │   ├── page.tsx                  # Landing page
│   │   ├── globals.css               # Estilos globais + dark mode
│   │   ├── login/page.tsx            # Página de login
│   │   └── dashboard/
│   │       ├── layout.tsx            # Layout com sidebar
│   │       ├── page.tsx              # Dashboard principal
│   │       └── bots/new/page.tsx     # Criar novo bot
│   ├── components/
│   │   ├── providers.tsx             # ThemeProvider
│   │   ├── sidebar.tsx               # Navegação lateral
│   │   ├── header.tsx                # Header com tema e notificações
│   │   ├── dashboard/
│   │   │   ├── stats-cards.tsx       # Cards de estatísticas
│   │   │   ├── bots-list.tsx         # Lista de bots
│   │   │   ├── recent-trades.tsx     # Trades recentes
│   │   │   └── pnl-chart.tsx         # Gráfico de P&L
│   │   └── forms/
│   │       ├── grid-config-form.tsx  # Form Grid com validação Zod
│   │       └── dca-config-form.tsx   # Form DCA com validação Zod
│   ├── lib/
│   │   ├── types.ts                  # TypeScript types
│   │   └── api.ts                    # API client
│   ├── package.json                  # Dependências Node.js
│   ├── tailwind.config.ts            # Configuração Tailwind
│   ├── tsconfig.json                 # Configuração TypeScript
│   ├── next.config.js                # Configuração Next.js
│   ├── postcss.config.js
│   ├── .eslintrc.json
│   └── Dockerfile
│
├── tests/                            # Testes Automatizados
│   ├── conftest.py                   # Fixtures pytest (mock exchange, orders, auth)
│   ├── unit/
│   │   ├── test_strategies.py        # Testes Grid e DCA
│   │   └── test_auth.py              # ✅ NOVO - Testes de autenticação (17 testes)
│   └── integration/
│       └── test_api.py               # Testes de API
│
├── db/
│   └── init.sql                      # Schema completo TimescaleDB
│                                     # (users, bots, orders, trades, metrics)
│
├── .github/workflows/
│   └── ci.yml                        # Pipeline: lint, test, build
│
├── docker-compose.yml                # 6 serviços: api, bot, celery, web, postgres, redis
├── Makefile                          # Comandos: install, dev, test, lint, docker-up
├── requirements.txt                  # Dependências Python
├── .gitignore                        # Ignores completos
├── .env.example                      # Template de variáveis
│
├── README.md                         # Documentação principal
├── CONTRIBUTING.md                   # Guia de contribuição
├── LICENSE                           # MIT License
├── CLAUDE.md                         # Instruções para Claude Code
│
├── PRD.md                            # Product Requirements Document
├── AutoGrid_TDD_v1.0.md              # Technical Design Document
├── AutoGrid_Sprint_backlog.md        # Sprint Backlog
└── AutoGrid-Wireframes.jsx           # Wireframes React
```

---

## Funcionalidades Implementadas (Stubs)

### API (FastAPI)
- [x] Health check endpoint
- [x] CORS configurado
- [x] Rotas de autenticação (register, login, refresh)
- [x] CRUD de bots (list, get, create, update, delete)
- [x] Start/Stop de bots
- [x] Endpoint de backtest
- [x] Schemas Pydantic completos

### Bot Engine
- [x] BaseStrategy ABC com métodos abstratos
- [x] Order dataclass com status tracking
- [x] GridStrategy com cálculo de grid levels
- [x] DCAStrategy com triggers de tempo e preço
- [x] ExchangeConnector ABC
- [x] CCXTConnector implementado
- [x] BotEngine com loop assíncrono

### Frontend (Next.js)
- [x] Landing page
- [x] Página de login
- [x] Dashboard layout com sidebar
- [x] Cards de estatísticas
- [x] Lista de bots com status
- [x] Gráfico de P&L (Recharts)
- [x] Trades recentes
- [x] Formulário Grid com validação
- [x] Formulário DCA com validação
- [x] Dark mode
- [x] API client

### Infraestrutura
- [x] Docker Compose completo
- [x] Dockerfiles otimizados
- [x] CI/CD com GitHub Actions
- [x] Schema de banco TimescaleDB
- [x] Makefile com comandos úteis

---

## Banco de Dados (TimescaleDB)

### Tabelas Criadas
| Tabela | Descrição | Hypertable |
|--------|-----------|------------|
| users | Usuários com planos (free/pro/enterprise) | Não |
| exchange_credentials | Credenciais criptografadas | Não |
| bots | Configuração dos bots | Não |
| orders | Ordens de compra/venda | Não |
| trades | Histórico de trades | Sim |
| bot_metrics | Métricas de performance | Sim |
| ohlcv_cache | Cache de candles | Sim |
| backtests | Resultados de backtests | Não |

### Features
- Compressão automática após 7 dias
- Índices otimizados para queries comuns
- Triggers de updated_at automáticos
- UUID como primary key

---

## Comandos Disponíveis

```bash
# Instalação
make install          # Instala dependências Python e Node.js

# Desenvolvimento
make dev              # Inicia API e frontend em modo dev
make docker-up        # Sobe todos os containers
make docker-down      # Para todos os containers
make docker-logs      # Visualiza logs

# Qualidade
make lint             # Roda linters (black, isort, flake8, mypy, eslint)
make format           # Formata código automaticamente
make test             # Roda testes com coverage

# Banco de Dados
make migrate          # Roda migrations Alembic
make db-shell         # Acessa psql do PostgreSQL
```

---

## Próximos Passos Sugeridos

### Sprint 1 - Fundação (Prioridade Alta)

#### 1. Configurar Ambiente de Desenvolvimento
```bash
# Criar .env a partir do template
cp .env.example .env
# Gerar chaves de segurança
openssl rand -hex 32  # Para ENCRYPTION_KEY
openssl rand -hex 32  # Para JWT_SECRET
# Subir containers
make docker-up
```

#### 2. Implementar Autenticação Real ✅
- [x] Integrar SQLAlchemy com PostgreSQL
- [x] Implementar hash de senhas (bcrypt)
- [x] Implementar JWT tokens (python-jose)
- [x] Criar middleware de autenticação
- [x] Adicionar rate limiting (código pronto em rate_limiter.py)

#### 3. Implementar CRUD de Bots Funcional
- [ ] Criar models SQLAlchemy
- [ ] Implementar repository pattern
- [ ] Conectar rotas aos services
- [ ] Validar permissões por usuário

#### 4. Implementar Conexão com Exchange
- [ ] Validar credenciais na criação
- [ ] Verificar permissões (trade sim, withdraw não)
- [ ] Criptografar API keys (Fernet)
- [ ] Implementar refresh de markets

### Sprint 2 - Core Trading

#### 5. Implementar Execução de Ordens
- [ ] Criar order manager
- [ ] Implementar order state machine
- [ ] Adicionar retry com exponential backoff
- [ ] Implementar circuit breaker

#### 6. Implementar Grid Trading Completo
- [ ] Colocar ordens iniciais
- [ ] Monitorar fills via WebSocket
- [ ] Recriar ordens após fill
- [ ] Calcular P&L em tempo real

#### 7. Implementar DCA Completo
- [ ] Scheduler para compras periódicas
- [ ] Detector de price drop
- [ ] Take profit automático
- [ ] Tracking de average entry

### Sprint 3 - Frontend & UX

#### 8. Integrar Frontend com API
- [ ] Implementar autenticação no frontend
- [ ] Criar hooks de data fetching (SWR/React Query)
- [ ] Implementar WebSocket para updates real-time
- [ ] Adicionar loading states e error handling

#### 9. Implementar Dashboard Real
- [ ] Conectar stats cards com API
- [ ] Gráfico de P&L real
- [ ] Lista de bots com status real-time
- [ ] Histórico de trades

#### 10. Implementar Visualização de Grid
- [ ] Componente de visualização do grid
- [ ] Mostrar ordens abertas no gráfico
- [ ] Indicar fills com animação

### Sprint 4 - Backtesting & Analytics

#### 11. Implementar Engine de Backtest
- [ ] Carregar dados históricos (CCXT)
- [ ] Simular execução de estratégia
- [ ] Calcular métricas (Sharpe, Drawdown, Win Rate)
- [ ] Gerar equity curve

#### 12. Implementar Relatórios
- [ ] Dashboard de performance por bot
- [ ] Exportar trades para CSV
- [ ] Comparar estratégias

### Sprint 5 - Telegram & Notificações

#### 13. Implementar Bot Telegram
- [ ] Comandos básicos (/status, /balance)
- [ ] Notificações de fills
- [ ] Alertas de erro
- [ ] Confirmação para stop

### Sprint 6 - Produção

#### 14. Preparar para Deploy
- [ ] Configurar secrets no GitHub
- [ ] Setup de monitoring (Prometheus/Grafana)
- [ ] Configurar alertas
- [ ] Documentar processo de deploy

---

## Arquitetura de Referência

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Next.js)                       │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │Dashboard│ │  Bots   │ │Backtest │ │Settings │ │  Login  │   │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘   │
└───────┼──────────┼──────────┼──────────┼──────────┼────────────┘
        │          │          │          │          │
        ▼          ▼          ▼          ▼          ▼
┌─────────────────────────────────────────────────────────────────┐
│                         API (FastAPI)                            │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐               │
│  │  Auth   │ │  Bots   │ │Backtest │ │Exchange │               │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘               │
└───────┼──────────┼──────────┼──────────┼───────────────────────┘
        │          │          │          │
        ▼          ▼          ▼          ▼
┌─────────────────────────────────────────────────────────────────┐
│                      BOT ENGINE (Celery)                         │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐               │
│  │GridStrategy │ │ DCAStrategy │ │OrderManager │               │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘               │
└─────────┼───────────────┼───────────────┼──────────────────────┘
          │               │               │
          ▼               ▼               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    EXCHANGE CONNECTOR (CCXT)                     │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐                           │
│  │ Binance │ │  MEXC   │ │  Bybit  │                           │
│  └─────────┘ └─────────┘ └─────────┘                           │
└─────────────────────────────────────────────────────────────────┘
          │               │               │
          ▼               ▼               ▼
┌─────────────────────────────────────────────────────────────────┐
│                         DATA LAYER                               │
│  ┌───────────────────┐ ┌───────────────────┐                   │
│  │ PostgreSQL/Timescale │ │      Redis        │                   │
│  │  (users, bots,     │ │  (cache, queues)  │                   │
│  │   orders, trades)  │ │                   │                   │
│  └───────────────────┘ └───────────────────┘                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Padrões de Código

### Python
- **Black** para formatação (line-length=88)
- **isort** para imports
- **flake8** para linting
- **mypy** para type checking
- **pytest** para testes

### TypeScript/React
- **ESLint** com regras Next.js
- **Prettier** via ESLint
- **strict: true** no tsconfig
- **Proibido usar `any`**

### Git
- Branch principal: `main`
- Conventional commits
- PRs obrigatórios para main

---

## Variáveis de Ambiente Necessárias

```env
# Banco de Dados
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/autogrid

# Redis
REDIS_URL=redis://localhost:6379

# Segurança (GERAR NOVOS VALORES!)
ENCRYPTION_KEY=<openssl rand -hex 32>
JWT_SECRET=<openssl rand -hex 32>

# Exchange (opcional para dev)
BINANCE_API_KEY=
BINANCE_API_SECRET=
BINANCE_TESTNET=true

# Telegram (opcional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

---

## Contato e Recursos

- **Repositório**: (configurar GitHub)
- **Documentação**: README.md, TDD, PRD
- **Issues**: GitHub Issues
- **Licença**: MIT

---

*Prompt gerado em: Dezembro 2025*
*Versão: 1.0.0*
