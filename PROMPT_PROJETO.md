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
│   │   ├── bots.py                   # CRUD de bots + start/stop (Celery dispatch)
│   │   ├── orders.py                 # ✅ NOVO - Ordens e trades por bot
│   │   ├── backtest.py               # Executar backtests
│   │   └── credentials.py            # ✅ NOVO - CRUD de credenciais + validação
│   ├── models/
│   │   ├── schemas.py                # Schemas Pydantic (User, Bot, Order)
│   │   └── orm.py                    # ✅ NOVO - SQLAlchemy ORM models
│   └── services/                     # ✅ Serviços implementados
│       ├── __init__.py
│       ├── security.py               # Hash de senhas (bcrypt)
│       ├── jwt.py                    # Criação/validação JWT
│       ├── user_service.py           # CRUD de usuários
│       ├── bot_service.py            # ✅ CRUD de bots + strategy_state persistence
│       ├── order_service.py          # ✅ NOVO - CRUD de ordens e trades
│       ├── encryption.py             # ✅ NOVO - Criptografia Fernet
│       └── credential_service.py     # ✅ NOVO - Gerenciamento de credenciais
│
├── bot/                              # Engine de Trading
│   ├── __init__.py
│   ├── engine.py                     # BotEngine com loop de execução + OrderManager/CircuitBreaker
│   ├── order_manager.py              # ✅ NOVO - Order state machine + lifecycle
│   ├── circuit_breaker.py            # ✅ NOVO - Kill switch (50 orders/min, 5% loss/hour)
│   ├── tasks.py                      # ✅ Celery tasks (start/stop, DCA scheduler, metrics)
│   ├── Dockerfile
│   ├── strategies/
│   │   ├── base.py                   # BaseStrategy ABC + Order dataclass
│   │   ├── grid.py                   # GridStrategy completo (bidirecional, P&L)
│   │   └── dca.py                    # ✅ DCAStrategy completo (scheduler, state)
│   └── exchange/
│       ├── connector.py              # ExchangeConnector ABC + CCXTConnector + retry
│       └── websocket_manager.py      # ✅ NOVO - WebSocket para Binance/Bybit
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
├── tests/                            # Testes Automatizados (208 testes)
│   ├── conftest.py                   # Fixtures pytest (mock exchange, orders, auth, bots)
│   ├── pytest.ini                    # Configuração pytest-asyncio
│   ├── unit/
│   │   ├── test_strategies.py        # Testes Grid e DCA
│   │   ├── test_auth.py              # ✅ Testes de autenticação (17 testes)
│   │   ├── test_bots.py              # ✅ Testes de CRUD bots (21 testes)
│   │   ├── test_credentials.py       # ✅ Testes de credenciais
│   │   ├── test_order_manager.py     # ✅ Testes OrderManager (47 testes)
│   │   ├── test_circuit_breaker.py   # ✅ Testes CircuitBreaker (38 testes)
│   │   ├── test_grid_strategy_complete.py  # ✅ Testes Grid completo (26 testes)
│   │   └── test_dca_strategy_complete.py   # ✅ NOVO - Testes DCA completo (53 testes)
│   └── integration/
│       └── test_api.py               # Testes de API (32 testes) + Orders endpoints
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

## Funcionalidades Implementadas

### API (FastAPI)
- [x] Health check endpoint
- [x] CORS configurado
- [x] ✅ **Autenticação completa** (register, login, refresh, /me)
- [x] ✅ **JWT tokens** com access/refresh
- [x] ✅ **Password hashing** com bcrypt
- [x] ✅ **SQLAlchemy ORM** com PostgreSQL async
- [x] ✅ **Middleware de autenticação** (get_current_user)
- [x] ✅ **CRUD de bots funcional** (list, get, create, delete) com BotService
- [x] ✅ **Start/Stop de bots** com validação de estado (stopped/running/paused/error)
- [x] Endpoint de backtest - protegido com auth
- [x] Schemas Pydantic completos
- [x] ✅ **Endpoints de ordens** (list, open, cancel por bot)
- [x] ✅ **Endpoints de trades** (list, statistics por bot)
- [x] ✅ **OrderService** para CRUD de ordens e trades

### Bot Engine
- [x] BaseStrategy ABC com métodos abstratos
- [x] Order dataclass com status tracking + grid_level
- [x] GridStrategy com cálculo de grid levels
- [x] ✅ **GridStrategy completo** (buy+sell bidirecional, GridLevel, position tracking)
- [x] ✅ **DCAStrategy completo** (scheduler, price drop, take profit, state persistence)
- [x] ExchangeConnector ABC
- [x] CCXTConnector implementado
- [x] BotEngine com loop assíncrono
- [x] ✅ **OrderManager** com state machine (PENDING → OPEN → FILLED/CANCELLED)
- [x] ✅ **CircuitBreaker** (50 orders/min, 5% loss/hour, 10% price deviation)
- [x] ✅ **WebSocketManager** para Binance e Bybit
- [x] ✅ **Retry com exponential backoff** no connector
- [x] ✅ **Celery tasks** para start/stop de bots + sync_bot_metrics (30s)
- [x] ✅ **Celery Beat DCA** (hourly/daily/weekly, price drops, take profit, state save)
- [x] ✅ **P&L Pipeline** (strategy → engine → circuit_breaker → database)

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
| users | Usuários com planos (free/starter/pro/enterprise) | Não |
| exchange_credentials | Credenciais criptografadas | Não |
| bots | Configuração dos bots + strategy_state (JSONB) | Não |
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

#### 3. Implementar CRUD de Bots Funcional ✅
- [x] Criar models SQLAlchemy (Bot, ExchangeCredential em orm.py)
- [x] Implementar repository pattern (BotService)
- [x] Conectar rotas aos services (6 endpoints funcionais)
- [x] Validar permissões por usuário (ownership check)

#### 4. Implementar Conexão com Exchange ✅
- [x] Validar credenciais na criação
- [x] Verificar permissões (trade sim, withdraw não)
- [x] Criptografar API keys (Fernet)
- [x] Implementar refresh de markets

### Sprint 2 - Core Trading

#### 5. Implementar Execução de Ordens ✅
- [x] ✅ Criar order manager (`bot/order_manager.py`)
- [x] ✅ Implementar order state machine (9 estados com transições validadas)
- [x] ✅ Adicionar retry com exponential backoff
- [x] ✅ Implementar circuit breaker (`bot/circuit_breaker.py`)
- [x] ✅ WebSocket para updates em real-time (Binance/Bybit)
- [x] ✅ Celery tasks para start/stop de bots
- [x] ✅ API endpoints para ordens e trades
- [x] ✅ 85 testes unitários e integração

#### 6. Implementar Grid Trading Completo ✅
- [x] ✅ Colocar ordens iniciais (buy + sell bidirecional)
- [x] ✅ Monitorar fills via WebSocket
- [x] ✅ Recriar ordens após fill (contra-ordens automáticas)
- [x] ✅ Calcular P&L em tempo real com persistência
- [x] ✅ GridLevel dataclass para tracking por nível
- [x] ✅ Celery task sync_bot_metrics (30s)
- [x] ✅ P&L no BotResponse da API
- [x] ✅ 26 testes unitários do grid completo

#### 7. Implementar DCA Completo ✅
- [x] ✅ Scheduler para compras periódicas (Celery Beat: hourly/daily/weekly)
- [x] ✅ Detector de price drop (task a cada 5 min)
- [x] ✅ Take profit automático (task a cada 5 min + execute_dca_sell)
- [x] ✅ Tracking de average entry (to_state_dict/from_state_dict + persistência)
- [x] ✅ Validação de parâmetros no DCAStrategy.__init__
- [x] ✅ 53 testes unitários cobrindo todos os cenários

### Sprint 3 - Frontend & UX

#### 8. Integrar Frontend com API ✅
- [x] ✅ Implementar autenticação no frontend (auth-context, middleware, API routes)
- [x] ✅ Criar hooks de data fetching (TanStack Query: use-bots, use-orders, use-trades, use-credentials, use-dashboard)
- [x] ✅ Implementar WebSocket para updates real-time (ws_manager, ws-context, use-realtime hooks)
- [x] ✅ Adicionar loading states e error handling (skeleton, error-boundary, toast, spinner)

#### 9. Implementar Dashboard Real ✅
- [x] ✅ Conectar stats cards com API (`web/components/dashboard/stats-cards.tsx`, `web/hooks/use-dashboard.ts`)
- [x] ✅ Gráfico de P&L real (`web/components/dashboard/pnl-chart.tsx`, `web/hooks/use-dashboard.ts`)
- [x] ✅ Lista de bots com status real-time (WebSocket invalidations em `web/lib/websocket/ws-context.tsx`)
- [x] ✅ Histórico de trades (`web/app/dashboard/trades/page.tsx`, `web/hooks/use-trades.ts`)

#### 10. Implementar Visualização de Grid ✅
- [x] ✅ Componente de visualização do grid (`web/components/dashboard/grid-visualization.tsx`)
- [x] ✅ Mostrar ordens abertas no gráfico (`web/hooks/use-grid-visualization.ts`)
- [x] ✅ Indicar fills com animação (`web/components/dashboard/grid-visualization.tsx`)

### Sprint 4 - Backtesting & Analytics

#### 11. Implementar Engine de Backtest ✅
- [x] ✅ Carregar dados históricos (CCXT) (`api/services/backtest_service.py`)
- [x] ✅ Simular execução de estratégia (`api/services/backtest_service.py`)
- [x] ✅ Calcular métricas (Sharpe, Drawdown, Win Rate) (`api/services/backtest_service.py`)
- [x] ✅ Gerar equity curve (`api/services/backtest_service.py`, `web/app/dashboard/backtest/page.tsx`)

#### 12. Implementar Relatórios ✅
- [x] ✅ Dashboard de performance por bot (`api/routes/reports.py`, `web/app/dashboard/reports/page.tsx`)
- [x] ✅ Exportar trades para CSV (`api/routes/reports.py`, `web/app/dashboard/reports/page.tsx`)
- [x] ✅ Comparar estratégias (`api/routes/reports.py`, `web/app/dashboard/reports/page.tsx`)

### Sprint 5 - Telegram & Notificações

#### 13. Implementar Bot Telegram
- [x] ✅ Comandos básicos (/status, /balance) (`api/routes/telegram.py`)
- [x] ✅ Notificações de fills (`bot/order_manager.py`, `api/services/telegram_service.py`)
- [x] ✅ Alertas de erro (`bot/engine.py`, `bot/tasks.py`, `api/services/telegram_service.py`)
- [x] ✅ Confirmação para stop (`api/routes/telegram.py`)

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
│  ┌─────────────┐ ┌─────────────┐ ┌──────────────┐              │
│  │GridStrategy │ │ DCAStrategy │ │ OrderManager │              │
│  └──────┬──────┘ └──────┬──────┘ └──────┬───────┘              │
│         │               │               │                       │
│         └───────────────┴───────┬───────┘                       │
│                                 ▼                               │
│                        ┌────────────────┐                       │
│                        │CircuitBreaker  │ ◄── Kill Switch       │
│                        │ (50 ord/min)   │     (Safety Limits)   │
│                        └────────┬───────┘                       │
└─────────────────────────────────┼───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    EXCHANGE CONNECTOR (CCXT)                     │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐  ┌────────────────────┐  │
│  │ Binance │ │  MEXC   │ │  Bybit  │  │ WebSocket Manager  │  │
│  └─────────┘ └─────────┘ └─────────┘  │ (Order Updates)    │  │
│                                        └────────────────────┘  │
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
TELEGRAM_WEBHOOK_URL=
TELEGRAM_WEBHOOK_SECRET=
TELEGRAM_BOT_USERNAME=
```

---

## Contato e Recursos

- **Repositório**: (configurar GitHub)
- **Documentação**: README.md, TDD, PRD
- **Issues**: GitHub Issues
- **Licença**: MIT

---

*Prompt gerado em: Dezembro 2025*
*Última atualização: 29/12/2025 - Sprint 5 Item 13 completo (Telegram bot, comandos e notificações)*
*Versão: 1.6.0*
