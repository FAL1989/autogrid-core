---
name: backtest-analysis
description: Analisar resultados de backtesting e interpretar métricas. Use quando o usuário tiver resultados de backtest, quiser entender Sharpe ratio, drawdown, win rate, ou comparar estratégias.
allowed-tools: Read, Grep, Glob
---

# Análise de Backtest

## Métricas Principais

### 1. Total Return (Retorno Total)
```
Fórmula: (valor_final - valor_inicial) / valor_inicial × 100

Exemplo: ($12,400 - $10,000) / $10,000 = 24%

Interpretação:
- > 0%: Estratégia lucrativa
- Comparar com benchmark (buy & hold)
```

### 2. Sharpe Ratio (Retorno Ajustado por Risco)
```
Fórmula: (retorno_médio - taxa_livre_risco) / desvio_padrão

Interpretação:
- < 0: Pior que investimento sem risco
- 0-1: Risco não compensa
- 1-2: Bom
- 2-3: Muito bom
- > 3: Excelente (verificar se é realista)
```

### 3. Max Drawdown (Maior Queda)
```
Fórmula: (pico - vale) / pico × 100

Exemplo: Portfólio caiu de $12,000 para $10,800
Drawdown = (12000 - 10800) / 12000 = 10%

Interpretação:
- < 10%: Baixo risco
- 10-20%: Moderado
- 20-30%: Alto
- > 30%: Muito arriscado
```

### 4. Win Rate (Taxa de Acerto)
```
Fórmula: trades_lucrativos / total_trades × 100

Interpretação:
- 50-60%: Aceitável se avg_win > avg_loss
- 60-70%: Bom
- > 70%: Excelente (verificar overfitting)
```

### 5. Profit Factor
```
Fórmula: lucro_bruto / perda_bruta

Interpretação:
- < 1: Prejuízo
- 1-1.5: Marginal
- 1.5-2: Bom
- > 2: Excelente
```

## Análise de Resultados

### Resultado Exemplo
```json
{
  "total_return": 0.24,
  "sharpe_ratio": 1.82,
  "max_drawdown": -0.084,
  "win_rate": 0.685,
  "profit_factor": 2.14,
  "total_trades": 342
}
```

### Interpretação
| Métrica | Valor | Avaliação |
|---------|-------|-----------|
| Retorno | 24% | Bom, supera S&P 500 (~10% a.a.) |
| Sharpe | 1.82 | Bom risco/retorno |
| Drawdown | -8.4% | Baixo risco |
| Win Rate | 68.5% | Excelente |
| Profit Factor | 2.14 | Excelente |
| Trades | 342 | Amostra estatística válida |

**Veredicto**: Estratégia robusta, pronta para paper trading.

## Red Flags (Sinais de Alerta)

### 1. Overfitting
- Sharpe > 3 em backtest
- Win rate > 80%
- Funciona só em período específico

**Solução**: Testar em período out-of-sample

### 2. Poucos Trades
- < 30 trades no backtest
- Resultados estatisticamente insignificantes

**Solução**: Aumentar período ou reduzir timeframe

### 3. Drawdown Alto
- Max drawdown > 30%
- Recuperação lenta

**Solução**: Reduzir tamanho de posição

### 4. Curva de Equity Irregular
- Grandes saltos
- Dependência de poucos trades

**Solução**: Diversificar ou ajustar estratégia

## Comparação com Benchmark

```
Estratégia Grid: +24%
Buy & Hold BTC: +15%
Alpha gerado: +9%

Conclusão: Estratégia supera holding passivo
```

## Próximos Passos

1. **Backtest OK** → Paper trading por 2-4 semanas
2. **Paper OK** → Live com 10% do capital planejado
3. **Live OK (1 mês)** → Escalar gradualmente

## Walk-Forward Analysis

Para validação robusta:
```
1. Otimizar em Jan-Jun (in-sample)
2. Testar em Jul-Set (out-of-sample)
3. Re-otimizar em Abr-Set
4. Testar em Out-Dez
5. Repetir...
```
