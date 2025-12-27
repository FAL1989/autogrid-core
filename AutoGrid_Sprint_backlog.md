
# AutoGrid Sprint Backlog & User Stories

## 18-Month Development Roadmap

- **Version:** 1.0  
- **Date:** December 27, 2025  
- **Sprint Duration:** 2 weeks  
- **Total Sprints:** 36 (18 months)  

---

## Overview

### Phase Summary

| Phase            | Timeline      | Focus                     | Deliverables                            |
|------------------|--------------|---------------------------|-----------------------------------------|
| Phase 1: MVP     | Months 1-3   | Open Source Core          | GitHub release, Grid + DCA              |
| Phase 2: Cloud   | Months 4-8   | Cloud Platform            | Dashboard, Telegram, Payments           |
| Phase 3: Scale   | Months 9-18  | Growth & Features         | White-label, API, Advanced              |

---

### Story Point Reference

| Points | Effort       | Description                                          |
|--------|--------------|------------------------------------------------------|
| 1      | ~2 hours     | Trivial change, config update, small bugfix          |
| 2      | ~4 hours     | Simple feature, single file change                   |
| 3      | ~1 day       | Standard feature, multiple files, some complexity    |
| 5      | ~2-3 days    | Complex feature, multiple components, integration    |
| 8      | ~1 week      | Major feature, significant complexity, research      |
| 13     | ~2 weeks     | Epic-level, should be broken down further            |

---

## Phase 1: MVP (Months 1-3)

**Goal:** Working open source bot on GitHub with Grid and DCA strategies. Validate market interest before building cloud platform.

### Sprint 1: Project Setup & Core Engine

**Sprint Goal:** Repository structure, CI/CD pipeline, and basic bot engine shell.

| ID  | User Story                                                                                                    | Points | Priority | Status |
|-----|--------------------------------------------------------------------------------------------------------------|--------|----------|--------|
| 1.1 | As a developer, I want to clone the repo and run locally in <5 min so I can start contributing               | 3      | HIGH     | To Do  |
| 1.2 | As a developer, I want automated tests to run on every PR so code quality stays high                        | 3      | HIGH     | To Do  |
| 1.3 | As a developer, I want a BaseStrategy interface so I can implement new strategies easily                     | 5      | HIGH     | To Do  |
| 1.4 | As a developer, I want Docker Compose setup so local dev environment is consistent                           | 2      | MED      | To Do  |

**Acceptance Criteria - Story 1.1:**
- [ ] README with clear setup instructions
- [ ] `docker-compose up` starts all services
- [ ] `make install` installs all Python dependencies
- [ ] `make test` runs test suite successfully

---

### Sprint 2: Exchange Connectivity

**Sprint Goal:** Connect to Binance testnet, fetch market data, execute paper trades.

| ID  | User Story                                                                                                    | Points | Priority | Status |
|-----|--------------------------------------------------------------------------------------------------------------|--------|----------|--------|
| 2.1 | As a user, I want to add my exchange API keys securely so the bot can trade on my behalf                     | 5      | HIGH     | To Do  |
| 2.2 | As a user, I want to see real-time prices so I know current market conditions                                | 5      | HIGH     | To Do  |
| 2.3 | As a user, I want the bot to reject API keys with withdraw permission so my funds stay safe                   | 3      | HIGH     | To Do  |

**Acceptance Criteria - Story 2.1:**
- [ ] API keys encrypted with AES-256 before storage
- [ ] Keys never appear in logs or error messages
- [ ] System validates keys against exchange API on save
- [ ] User can update or delete keys

---

### Sprint 3: Grid Strategy Implementation

**Sprint Goal:** Fully functional Grid bot executing trades on testnet.

| ID  | User Story                                                                                                    | Points | Priority | Status |
|-----|--------------------------------------------------------------------------------------------------------------|--------|----------|--------|
| 3.1 | As a trader, I want to configure a Grid bot with price range and grid count so I can profit from sideways markets | 8      | HIGH     | To Do  |
| 3.2 | As a trader, I want the bot to automatically place buy orders below and sell orders above current price       | 5      | HIGH     | To Do  |
| 3.3 | As a trader, I want the bot to replace filled orders so the grid stays active                                 | 5      | HIGH     | To Do  |

**Acceptance Criteria - Story 3.1:**
- [ ] User specifies: symbol, lower_price, upper_price, grid_count, investment
- [ ] Bot calculates grid spacing: (upper - lower) / grid_count
- [ ] Bot validates minimum order size per exchange
- [ ] Configuration persisted to database

---

### Sprint 4: DCA Strategy & Kill Switch

**Sprint Goal:** DCA bot implementation and safety circuit breakers.

| ID  | User Story                                                                                                    | Points | Priority | Status |
|-----|--------------------------------------------------------------------------------------------------------------|--------|----------|--------|
| 4.1 | As a trader, I want a DCA bot that buys at regular intervals so I reduce timing risk                         | 5      | HIGH     | To Do  |
| 4.2 | As a trader, I want the bot to stop automatically if losses exceed threshold so I don't lose everything       | 5      | HIGH     | To Do  |
| 4.3 | As a trader, I want to be notified when the bot triggers a kill switch so I can investigate                   | 3      | MED      | To Do  |

---

### Sprint 5: Backtesting Engine

**Sprint Goal:** Historical simulation with key performance metrics.

| ID  | User Story                                                                                                    | Points | Priority | Status |
|-----|--------------------------------------------------------------------------------------------------------------|--------|----------|--------|
| 5.1 | As a trader, I want to test my strategy on historical data so I know if it would have been profitable         | 8      | HIGH     | To Do  |
| 5.2 | As a trader, I want to see Sharpe ratio, max drawdown, and win rate so I can evaluate risk                   | 3      | HIGH     | To Do  |
| 5.3 | As a trader, I want to download historical data from exchange so backtests use real market conditions          | 5      | MED      | To Do  |

---

### Sprint 6: CLI & Documentation

**Sprint Goal:** Complete CLI interface and documentation for GitHub release.

| ID  | User Story                                                                                                    | Points | Priority | Status |
|-----|--------------------------------------------------------------------------------------------------------------|--------|----------|--------|
| 6.1 | As a user, I want a CLI to manage bots so I can run everything from terminal                                  | 5      | HIGH     | To Do  |
| 6.2 | As a user, I want comprehensive README so I can set up the bot without asking for help                        | 3      | HIGH     | To Do  |
| 6.3 | As a contributor, I want CONTRIBUTING.md so I know how to submit PRs                                          | 2      | MED      | To Do  |
| 6.4 | As a user, I want exchange affiliate links so I can support the project when signing up                       | 2      | MED      | To Do  |

**CLI Commands:**
- `autogrid init` — Initialize config file
- `autogrid credentials add` — Add exchange API keys
- `autogrid bot create` — Create new bot
- `autogrid bot start/stop` — Control bots
- `autogrid bot list` — Show all bots
- `autogrid backtest` — Run backtest

---

## Phase 2: Cloud Platform (Months 4-8)

**Goal:** Web dashboard, user authentication, Telegram bot, and payment processing.

---

### Sprint 7-8: User Authentication & Dashboard

| ID  | User Story                                                                                                    | Points | Priority | Status |
|-----|--------------------------------------------------------------------------------------------------------------|--------|----------|--------|
| 7.1 | As a user, I want to register with email/password so I have my own account                                   | 5      | HIGH     | To Do  |
| 7.2 | As a user, I want to see my portfolio value and P&L on a dashboard                                           | 8      | HIGH     | To Do  |
| 7.3 | As a user, I want to create and manage bots via web UI instead of CLI                                        | 8      | HIGH     | To Do  |
| 7.4 | As a user, I want to see my trade history with filters and export                                            | 5      | MED      | To Do  |

---

### Sprint 9-10: Payments & Subscription

| ID  | User Story                                                                                                    | Points | Priority | Status |
|-----|--------------------------------------------------------------------------------------------------------------|--------|----------|--------|
| 9.1 | As a user, I want to subscribe to a paid plan with credit card via Stripe                                    | 8      | HIGH     | To Do  |
| 9.2 | As a user, I want feature limits enforced based on my plan (bots, exchanges)                                 | 5      | HIGH     | To Do  |
| 9.3 | As a user, I want to upgrade/downgrade my plan anytime                                                       | 3      | MED      | To Do  |

---

### Sprint 11-12: Telegram Bot

| ID    | User Story                                                                                                | Points | Priority | Status |
|-------|-----------------------------------------------------------------------------------------------------------|--------|----------|--------|
| 11.1  | As a user, I want to connect my Telegram account to receive trade alerts                                  | 5      | HIGH     | To Do  |
| 11.2  | As a user, I want to execute trades via Telegram commands (/buy, /sell)                                   | 8      | HIGH     | To Do  |
| 11.3  | As a user, I want to check my portfolio via /portfolio command                                            | 3      | MED      | To Do  |
| 11.4  | As a platform owner, I want to charge 0.5% fee per Telegram trade                                         | 5      | HIGH     | To Do  |

---

## Phase 3: Scale (Months 9-18)

**Goal:** White-label, public API, advanced features, and growth to \$20k MRR.

### Key Epics

| Sprint   | Epic                   | Est. Points | Key Deliverable             |
|----------|------------------------|-------------|-----------------------------|
| 13-16    | More Exchanges         | 21          | KuCoin, OKX, Kraken         |
| 17-20    | Advanced Backtesting   | 34          | Parameter optimization      |
| 21-24    | Public API             | 26          | REST API for integrations   |
| 25-30    | White-Label Telegram   | 40          | Custom bots for communities |
| 31-36    | Strategy Marketplace   | 55          | Community strategies        |

---

## Backlog Summary

### Total Story Points by Phase

| Phase           | Sprints | Est. Points | Stories |
|-----------------|---------|-------------|---------|
| Phase 1: MVP    | 6       | ~85         | 22      |
| Phase 2: Cloud  | 10      | ~120        | 35      |
| Phase 3: Scale  | 20      | ~180        | 45      |
| **TOTAL**       | 36      | ~385        | 102     |

---

### Velocity Assumptions

- Solo developer: ~15-20 points per sprint  
- Small team (2-3): ~30-40 points per sprint  
- Adjustment: Re-estimate after first 3 sprints based on actual velocity

---

### Definition of Done

- [ ] Code written and peer reviewed
- [ ] Unit tests passing (>80% coverage)
- [ ] Integration tests passing
- [ ] Documentation updated
- [ ] Deployed to staging
- [ ] Product owner acceptance

---

_AutoGrid Sprint Backlog v1.0 | December 2025_

