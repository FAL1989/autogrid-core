---
name: dca-configuration
description: Configurar DCA Bots (Dollar Cost Averaging). Use quando o usuário quiser criar um bot DCA, definir intervalos de compra, triggers de preço, ou estratégias de acumulação.
allowed-tools: Read, Grep, Glob
---

# Configuração de DCA Bot

## O que é DCA (Dollar Cost Averaging)?

DCA é uma estratégia de comprar um ativo em intervalos regulares ou em quedas de preço, reduzindo o preço médio de entrada e o risco de timing.

## Tipos de DCA

### 1. DCA por Tempo
Compra em intervalos fixos independente do preço.

```json
{
  "type": "time_based",
  "interval": "daily",  // hourly, daily, weekly, monthly
  "amount": 100,        // USDT por compra
  "symbol": "BTC/USDT"
}
```

### 2. DCA por Queda de Preço
Compra quando o preço cai X% do último ponto.

```json
{
  "type": "price_drop",
  "trigger_drop": 5,     // % de queda para trigger
  "amount": 100,
  "max_orders": 10,      // máximo de ordens de safety
  "symbol": "ETH/USDT"
}
```

### 3. DCA Híbrido
Combina tempo + queda de preço.

```json
{
  "type": "hybrid",
  "base_interval": "weekly",
  "base_amount": 50,
  "extra_on_drop": true,
  "drop_threshold": 10,
  "extra_amount": 100
}
```

## Parâmetros Necessários

| Parâmetro | Descrição | Exemplo |
|-----------|-----------|---------|
| `symbol` | Par de trading | ETH/USDT |
| `base_amount` | Valor base por compra | $100 |
| `interval` | Frequência | daily/weekly |
| `total_investment` | Limite total | $5,000 |
| `take_profit` | % para vender tudo | 30% |

## Cálculos

```python
# Preço médio após N compras
average_price = total_spent / total_quantity

# Break-even com fees (0.1% por trade)
break_even = average_price * 1.002  # 0.1% compra + 0.1% venda

# Lucro necessário para TP
required_gain = (take_profit / 100) + 0.002
```

## Safety Orders (Ordens de Segurança)

Para DCA por queda, configure safety orders:

```json
{
  "safety_orders": [
    { "drop": 5, "amount": 100 },   // -5%: compra $100
    { "drop": 10, "amount": 150 },  // -10%: compra $150
    { "drop": 15, "amount": 200 },  // -15%: compra $200
    { "drop": 20, "amount": 300 }   // -20%: compra $300
  ],
  "max_safety_orders": 4,
  "total_safety_budget": 750
}
```

## Recomendações por Objetivo

### Acumulação de Longo Prazo
- Intervalo: Semanal ou mensal
- Sem take profit automático
- Ignorar volatilidade de curto prazo

### Trading Ativo
- DCA por queda de preço
- Take profit: 10-20%
- Safety orders agressivos

### Conservador
- Intervalo: Mensal
- Apenas blue chips (BTC, ETH)
- Budget limitado por mês

## Exemplo Completo

```json
{
  "name": "ETH Acumulação",
  "strategy": "dca",
  "symbol": "ETH/USDT",
  "config": {
    "type": "hybrid",
    "base_amount": 50,
    "interval": "weekly",
    "drop_threshold": 10,
    "extra_amount": 100,
    "take_profit": 30,
    "stop_loss": null,
    "total_budget": 2000
  }
}
```

## Checklist Antes de Iniciar

- [ ] Budget total definido
- [ ] Intervalo alinhado com objetivo
- [ ] Safety orders calculados
- [ ] Fundos suficientes na exchange
- [ ] Alertas configurados
