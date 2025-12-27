
# AutoGrid

## Product Requirements Document (PRD)

### The Open Source Trading Bot for Everyone  
**Open Source Core • Cloud Platform • Affiliate Revenue**

---

**Version:** 1.0  
**Date:** December 27, 2025  
**Author:** Fernando \| F.A.L AI Agency  
**Status:** In Development  
**Target Market:** Global (English-first)  

---

## 1. Executive Summary

### 1.1 Product Vision

AutoGrid é a alternativa open source ao 3Commas e Cryptohopper. Combina um bot de trading grátis, autohospedado, com hospedagem em nuvem opcional e integração com Telegram. Nosso posicionamento: **"O mais simples robô grid que realmente funciona"** — direcionado a iniciantes que se sentem perdidos em plataformas complexas e desenvolvedores que buscam transparência e personalização.

### 1.2 Oportunidade de Mercado

O mercado global de bots de trading ultrapassa US$ 2,5 bilhões por ano. Soluções existentes são complexas (Hummingbot, Freqtrade) ou caras (US$ 50–300/mês). O AutoGrid atende o meio termo: quem deseja automação sem complexidade ou custo alto. O core open-source gera confiança e uma comunidade, enquanto monetizamos com serviços em nuvem e parcerias afiliadas.

### 1.3 Modelo de Negócios

1. **Open Source Core:** Bot MIT-gratuito no GitHub para credibilidade e comunidade  
2. **AutoGrid Cloud:** Hospedagem gerenciada e recursos premium (US$ 9–49/mês)  
3. **Telegram Bot:** Execução de trades via chat, 0,5% de taxa por transação  
4. **Receita de Afiliados:** Comissão de 50–70% de exchanges (MEXC, Binance, Bybit)  

### 1.4 Benchmark - Competidores

| Feature           | AutoGrid | 3Commas | Pionex | Freqtrade |
|-------------------|:--------:|:-------:|:------:|:---------:|
| Open Source       | ✓        | ✗       | ✗      | ✓         |
| Cloud Option      | ✓        | ✓       | ✓      | ✗         |
| Beginner Friendly | ✓        | Médio   | ✓      | ✗         |
| Starting Price    | Free     | $49/mês | Free*  | Free      |
| Telegram Bot      | ✓        | ✓       | ✗      | ✓         |

\* Pionex é gratuito mas exige usar exclusivamente sua exchange.

---

## 2. Problema & Oportunidade

### 2.1 Problemas Resolvidos

#### Para Traders Iniciantes
- Bots existentes são complexos, com muitas opções e jargões
- Plataformas pagas custam $50–300/mês – caro para experimentar
- Medo de perder dinheiro por decisões emocionais/manuais
- Não conseguem validar estratégias sem arriscar dinheiro real

#### Para Devs/Power Users
- Plataformas fechadas são black-box — impossível auditar algoritmos
- Alternativas open source (Freqtrade) têm curva de aprendizado íngreme
- Querem customizar estratégias sem partir do zero

### 2.2 Tamanho do Mercado

| Segmento              | TAM (Global)       | SAM (Addressable) |
|-----------------------|--------------------|------------------|
| Trading Bots SaaS     | $2.5B              | $500M            |
| Crypto Retail Traders | 420M+ usuários     | 50M ativos       |
| Exchange Affiliates   | $500M+             | $50M             |

---

## 3. Personas de Usuário

### 3.1 Primário: O Iniciante Curioso
- **Perfil:** Alex, 28, marketing, trades nos fins de semana
- **Capital:** $500–5.000
- **Dor:** Perde oportunidades enquanto dorme/trabalha, opera emocionalmente
- **Necessita:** Setup simples, estratégias prontas, alertas via Telegram, baixo custo

### 3.2 Secundário: O Dev Trader
- **Perfil:** Sam, 32, engenheiro de software, quer automatizar renda extra
- **Capital:** $5.000–50.000
- **Dor:** Não confia em plataformas black-box, quer auditar código
- **Necessita:** Open source, extensível, boa documentação, opção cloud

### 3.3 Terciário: O Líder de Comunidade
- **Perfil:** Jordan, 35, lidera grupo de 10K traders no Discord/Telegram
- **Dor:** Quer monetizar comunidade sem vender cursos/sinais
- **Necessita:** Telegram bot white-label, revenue share, marca customizada

---

## 4. Funcionalidades

### 4.1 Fase 1: MVP (1-3 meses)
- **Objetivo:** Validar demanda com investimento mínimo; bot open source funcional e primeiras receitas afiliadas

#### 4.1.1 AutoGrid Core (Open Source)
1. Grid Bot: Compra/venda automatizada em ranges configuráveis
2. DCA Bot: Dólar Cost Averaging com triggers customizáveis
3. Multi-Exchange: Binance, MEXC, Bybit via CCXT
4. Backtesting: Simulação histórica (Sharpe, drawdown, etc)
5. CLI Interface: Linha de comando para devs
6. Documentação: README completa, exemplos, guia de contribuição

### 4.2 Fase 2: Cloud Platform (4-8 meses)
#### 4.2.1 AutoGrid Cloud
- 24/7 Hosting: Infra gerenciada, SLA 99,9%
- Web Dashboard: Interface visual, configura estratégias sem código
- Multi-Channel Alerts: Telegram, Email, Discord
- Trade History: Log completo, P&L, métricas de performance
- Multiple Bots: Gerencie múltiplos bots em diferentes exchanges

#### 4.2.2 Telegram Bot
- Quick Trade: Ordena via chat
- Portfolio View: Balances e posições em tempo real
- Alerts: Notificação de trades executados
- Monetização: 0,5% por transação via bot

### 4.3 Fase 3: Escala (9-18 meses)
- Backtesting avançado: otimização por ML
- Strategy Marketplace: Estratégias da comunidade
- White-Label: Bots Telegram customizados
- Public API: Integrações de terceiros

---

## 5. Arquitetura Técnica

### 5.1 Stack Tecnológica

| Componente          | Tecnologia                | Motivo                                  |
|---------------------|--------------------------|-----------------------------------------|
| Backend Core        | Python 3.11+             | Ecossistema trading (CCXT, pandas...)   |
| REST API            | FastAPI                  | Async nativo, docs OpenAPI automáticos  |
| Frontend            | Next.js 14 + Tailwind    | SSR, ótimo DX, rápido                   |
| Database            | PostgreSQL + TimescaleDB | Time-series, otimizado para trading     |
| Exchange Connector  | CCXT                     | 100+ exchanges, manutenção ativa        |
| Infraestrutura      | DigitalOcean + Docker    | Baixo custo, fácil escala, regiões      |

### 5.2 Segurança

- API Keys: Criptografadas (AES-256), nunca logadas
- Permissões: Apenas trade, nunca saque
- Rate Limiting: Por IP e usuário – contra abuso
- Audit Log: Toda ação registrada (timestamp e IP)
- Kill Switch: Circuit breaker automático em anomalias

---

## 6. Modelo de Negócios

### 6.1 Planos e Preços

| Plano               | Preço     | Bots      | Features                                    |
|---------------------|-----------|-----------|---------------------------------------------|
| Free (Open Source)  | $0        | Ilimitado | Self-host, CLI, 1 exchange                  |
| Starter Cloud       | $9/mês    | 2         | Cloud, dashboard, 2 exchanges               |
| Pro Cloud           | $29/mês   | 10        | Telegram Bot, backtesting, 5 exchanges      |
| Enterprise          | $49+/mês  | Ilimitado | API, white-label, suporte dedicado          |

### 6.2 Projeções de Receita (18 meses)

| Receita              | Mês 6 | Mês 12 | Mês 18 |
|----------------------|-------|--------|--------|
| SaaS Subscriptions   | $1.500| $5.000 | $12.000|
| Telegram Bot Fees    | $300  | $1.500 | $4.000 |
| Affiliate Commission | $500  | $2.000 | $4.000 |
| **TOTAL MRR**        | $2.300| $8.500 | $20.000|

**Meta:** $20.000/mês de MRR no mês 18 (~$660/dia renda passiva)

---

## 7. Roadmap

### 7.1 Fase 1: Foundation (1-3 meses)
| Sprint | Entregáveis                                | Métricas de Sucesso                       |
|--------|-------------------------------------------|-------------------------------------------|
| 1-2    | Core bot engine, Grid strategy, CCXT      | Bot executa trades no testnet             |
| 3-4    | DCA, backtesting básico, CLI              | Backtest retorna métricas                 |
| 5-6    | GitHub release, docs, afiliados           | 100 estrelas, 20 clones, 10 afiliados     |

### 7.2 Fase 2: Product (4-8 meses)
| Sprint | Entregáveis                                | Métricas de Sucesso                         |
|--------|-------------------------------------------|---------------------------------------------|
| 7-10   | Cloud infra, user auth, bot hosting       | 10 beta users rodando bots                  |
| 11-14  | Web dashboard, Stripe                     | 50 usuários pagantes                        |
| 15-16  | Telegram bot MVP, exec. de trades         | 100+ trades pelo Telegram                   |

### 7.3 Fase 3: Escala (9-18 meses)
| Sprint | Entregáveis                         | Métricas de Sucesso                 |
|--------|-------------------------------------|-------------------------------------|
| 17-24  | Backtesting avançado, +exchanges    | 200 usuários pagantes               |
| 25-32  | White-label, API pública            | 5 partners white-label              |
| 33-36  | Marketplace, ML optimization        | 500+ usuários, $20k MRR             |

---

## 8. Riscos & Mitigações

| Risco                        | Prob.   | Impacto              | Mitigação                              |
|------------------------------|---------|----------------------|----------------------------------------|
| Bug causa prejuízo financeiro| Médio   | Reputação, processos | Kill switch, testes, ToS claro         |
| Exchange bloqueia API        | Baixo   | Perda de função      | Multi-exchange já no MVP               |
| Concorrente investido        | Alto    | Perda do mercado     | Moat open source, nicho, comunidade    |
| Bear market prolongado       | Médio   | Menos usuários       | DCA bots funcionam melhor em bear      |
| Regulatório                  | Médio   | Compliance           | Só software, sem consultoria financeira|

---

## 9. Métricas de Sucesso

| Métrica        | Mês 6 | Mês 12 | Mês 18 |
|----------------|-------|--------|--------|
| MRR            | $2.300| $8.500 | $20.000|
| Usuários pagos | 100   | 300    | 600+   |
| GitHub Stars   | 500   | 1.500  | 3.000+ |
| Churn mensal   | <12%  | <8%    | <6%    |
| NPS            | >30   | >45    | >55    |

### 9.1 Go/No-Go Checkpoints

- **Mês 3:** Se <100 GitHub stars ou 0 beta users → Pivot ou fim
- **Mês 6:** Se <20 usuários pagos ou <$1.000 MRR → Rever pricing/posicionamento
- **Mês 12:** Se <$5.000 MRR → Considerar pivot p/consultoria

---

## 10. Próximos Passos Imediatos

1. Semana 1: Setup do GitHub, estrutura de pastas, CI/CD pipeline
2. Semana 2: Integrar CCXT com Binance testnet
3. Semana 3: Grid bot funcional em paper trading
4. Semana 4: Documentação, primeiro alpha release
5. Semana 5: Setup afiliados MEXC/Binance, landing page básica

---

**— END OF DOCUMENT —**

AutoGrid PRD v1.0 \| Dezembro 2025  
Confidencial — Não distribua sem autorização.

