---
name: grid-configuration
description: Configurar Grid Bots com parâmetros otimizados. Use quando o usuário quiser criar um grid bot, definir range de preços, calcular grid spacing, ou otimizar configurações de grid trading.
allowed-tools: Read, Grep, Glob
---

# Configuração de Grid Bot

## O que é Grid Trading?

Grid trading coloca ordens de compra e venda em intervalos fixos de preço dentro de um range. Lucra com a volatilidade lateral do mercado.

## Parâmetros Necessários

| Parâmetro | Descrição | Exemplo |
|-----------|-----------|---------|
| `symbol` | Par de trading | BTC/USDT |
| `lower_price` | Limite inferior do grid | $40,000 |
| `upper_price` | Limite superior do grid | $48,000 |
| `grid_count` | Número de grids | 20 |
| `investment` | Capital total | $1,000 |

## Cálculos Automáticos

```python
# Grid spacing
grid_spacing = (upper_price - lower_price) / grid_count
# Exemplo: (48000 - 40000) / 20 = $400 por grid

# Investimento por grid
per_grid = investment / grid_count
# Exemplo: 1000 / 20 = $50 por grid

# Lucro por grid (sem fees)
profit_per_grid = grid_spacing / lower_price
# Exemplo: 400 / 40000 = 1% por grid
```

## Regras de Validação

1. **Range de preço**: `upper_price` deve ser > `lower_price`
2. **Grid count**: Entre 5 e 100 (recomendado: 10-30)
3. **Investimento mínimo**: Verificar min order size da exchange
4. **Volatilidade**: Range deve cobrir volatilidade esperada

## Recomendações por Mercado

### Mercado Lateral (Sideways)
- Grid count: 15-25
- Range: ±10-15% do preço atual
- Melhor cenário para grid trading

### Mercado Volátil
- Grid count: 10-15
- Range: ±20-30% do preço atual
- Maior lucro por grid, menos trades

### Mercado Estável
- Grid count: 25-40
- Range: ±5-10% do preço atual
- Mais trades, menor lucro por grid

## Exemplo de Configuração

```json
{
  "name": "BTC Grid Moderado",
  "strategy": "grid",
  "symbol": "BTC/USDT",
  "config": {
    "lower_price": 40000,
    "upper_price": 48000,
    "grid_count": 20,
    "investment": 1000,
    "take_profit": 25,
    "stop_loss": 10
  }
}
```

## Checklist Antes de Iniciar

- [ ] Range cobre volatilidade esperada
- [ ] Investimento por grid > min order size
- [ ] Exchange tem liquidez suficiente
- [ ] API keys configuradas (sem withdraw)
- [ ] Kill switch configurado
