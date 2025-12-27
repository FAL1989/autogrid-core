---
name: troubleshooting
description: Resolver problemas comuns do AutoGrid. Use quando o usuário tiver erros, bots não executando, ordens falhando, ou qualquer problema técnico com o sistema.
allowed-tools: Read, Grep, Glob, Bash
---

# Troubleshooting AutoGrid

## Diagnóstico Rápido

```bash
# Status geral do sistema
docker-compose ps

# Logs do bot engine
docker-compose logs -f bot-engine

# Logs da API
docker-compose logs -f api

# Verificar conexão com banco
docker-compose exec postgres pg_isready
```

## Problemas Comuns

### 1. Bot Não Inicia

**Sintomas**: Status "stopped" ou "error"

**Verificar**:
```bash
# Logs do bot específico
docker-compose logs bot-engine | grep "bot_id"

# Status das credenciais
curl http://localhost:8000/credentials -H "Authorization: Bearer $TOKEN"
```

**Causas comuns**:
- API keys inválidas ou expiradas
- Saldo insuficiente na exchange
- Par de trading não existe
- Rate limit excedido

**Solução**:
```bash
# Revalidar credenciais
autogrid credentials test

# Verificar saldo
autogrid balance --exchange binance
```

### 2. Ordens Não Executam

**Sintomas**: Ordens ficam "pending" indefinidamente

**Verificar**:
```bash
# Ordens pendentes
autogrid orders list --status pending

# Logs de ordem específica
docker-compose logs bot-engine | grep "order_id"
```

**Causas comuns**:
- Preço fora do mercado
- Quantidade abaixo do mínimo
- Fundos insuficientes
- Exchange em manutenção

**Solução**:
```python
# Verificar min order size
import ccxt
exchange = ccxt.binance()
markets = exchange.load_markets()
print(markets['BTC/USDT']['limits'])
```

### 3. Kill Switch Disparou

**Sintomas**: Bot parou automaticamente, notificação recebida

**Verificar**:
```bash
# Logs do kill switch
docker-compose logs bot-engine | grep "kill_switch"

# Histórico de ordens recentes
autogrid orders list --last 1h
```

**Causas possíveis**:
- Perda > 5% em 1 hora
- > 50 ordens/minuto
- Ordem > 10% do preço de mercado
- Anomalia detectada

**Próximos passos**:
1. Analisar causa do trigger
2. Verificar se foi falso positivo
3. Ajustar configurações se necessário
4. Reiniciar bot manualmente

### 4. Conexão WebSocket Caindo

**Sintomas**: Dados atrasados, reconexões frequentes

**Verificar**:
```bash
# Status do WebSocket
docker-compose logs bot-engine | grep "websocket"

# Ping para exchange
ping api.binance.com
```

**Solução**:
```python
# Aumentar timeout no config
{
  "websocket": {
    "ping_interval": 30,
    "reconnect_delay": 5,
    "max_reconnect_attempts": 10
  }
}
```

### 5. Erro de Database

**Sintomas**: "Connection refused", "Too many connections"

**Verificar**:
```bash
# Status do PostgreSQL
docker-compose exec postgres pg_isready

# Conexões ativas
docker-compose exec postgres psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"
```

**Solução**:
```bash
# Reiniciar banco
docker-compose restart postgres

# Aumentar max_connections
# Em postgresql.conf: max_connections = 200
```

### 6. Backtest Lento ou Travando

**Sintomas**: Backtest demora muito ou não termina

**Causas**:
- Período muito longo
- Dados OHLCV não cacheados
- Memória insuficiente

**Solução**:
```bash
# Pré-carregar dados
autogrid data download --symbol BTC/USDT --start 2024-01-01 --end 2024-12-31

# Usar timeframe maior
autogrid backtest --timeframe 1h  # ao invés de 1m
```

## Logs Importantes

| Arquivo | Conteúdo |
|---------|----------|
| `bot-engine.log` | Execução de estratégias, ordens |
| `api.log` | Requests HTTP, autenticação |
| `celery.log` | Tasks assíncronas, DCA triggers |

## Health Checks

```bash
# Script de diagnóstico completo
autogrid doctor

# Saída esperada:
# ✓ Database: Connected
# ✓ Redis: Connected
# ✓ Binance API: Accessible
# ✓ Bot Engine: Running
# ✓ Celery Workers: 4 active
```

## Suporte

Se o problema persistir:
1. Coletar logs: `docker-compose logs > debug.log`
2. Abrir issue no GitHub com logs anexados
3. Não incluir API keys nos logs!
