---
name: exchange-setup
description: Configurar conexão com exchanges (Binance, MEXC, Bybit). Use quando o usuário quiser conectar uma exchange, criar API keys, ou resolver problemas de autenticação.
allowed-tools: Read, Grep, Glob
---

# Configuração de Exchange

## Exchanges Suportadas

| Exchange | Spot | Futures | WebSocket | Testnet |
|----------|------|---------|-----------|---------|
| Binance | ✓ | ✓ | ✓ | ✓ |
| MEXC | ✓ | ✗ | Limitado | ✗ |
| Bybit | ✓ | ✓ | ✓ | ✓ |

## Criando API Keys

### Binance

1. Acesse [binance.com/api-management](https://www.binance.com/en/my/settings/api-management)
2. Clique em "Create API"
3. Escolha "System generated"
4. Configure permissões:
   - ✅ Enable Reading
   - ✅ Enable Spot & Margin Trading
   - ❌ Enable Withdrawals (NUNCA!)
   - ❌ Enable Futures (opcional)
5. Configure IP Whitelist (recomendado)
6. Salve API Key e Secret

### MEXC

1. Acesse [mexc.com/user/openapi](https://www.mexc.com/user/openapi)
2. Clique em "Create API"
3. Configure:
   - ✅ Read
   - ✅ Trade
   - ❌ Withdraw (NUNCA!)
4. Configure IP restriction
5. Salve as credenciais

### Bybit

1. Acesse [bybit.com/app/user/api-management](https://www.bybit.com/app/user/api-management)
2. Clique em "Create New Key"
3. Escolha "System-generated API Keys"
4. Configure:
   - ✅ Read
   - ✅ Trade
   - ❌ Withdraw (NUNCA!)
5. Configure IP whitelist
6. Salve as credenciais

## Segurança Obrigatória

### ✅ DEVE ter
- Permissão de leitura (Read)
- Permissão de trade (Trade/Spot)
- IP Whitelist configurado

### ❌ NUNCA deve ter
- Permissão de saque (Withdraw)
- Permissão de transferência interna
- IP aberto (sem whitelist)

## Testando Conexão

### Via CLI
```bash
autogrid credentials add --exchange binance
# Digite API Key e Secret quando solicitado

autogrid credentials test
# Deve mostrar: "Connection successful"
```

### Via API
```bash
curl -X POST http://localhost:8000/credentials \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "exchange": "binance",
    "api_key": "sua_api_key",
    "api_secret": "seu_secret"
  }'
```

## Testnet (Recomendado para Início)

### Binance Testnet
1. Acesse [testnet.binance.vision](https://testnet.binance.vision/)
2. Faça login com GitHub
3. Gere API keys de teste
4. Use fundos fictícios para testar

### Bybit Testnet
1. Acesse [testnet.bybit.com](https://testnet.bybit.com/)
2. Registre conta separada
3. Gere API keys de teste

## Troubleshooting

### Erro: "Invalid API Key"
- Verificar se copiou key completa
- Verificar se não há espaços extras
- Key pode ter expirado

### Erro: "IP not whitelisted"
- Adicionar IP do servidor na exchange
- Para IP dinâmico, considerar VPN com IP fixo

### Erro: "Permission denied"
- Verificar se permissão de trade está ativa
- Algumas exchanges requerem KYC para API

### Erro: "Signature invalid"
- API Secret incorreto
- Problema de encoding (caracteres especiais)
- Clock do servidor dessincronizado

## Rate Limits

| Exchange | Limite | Recomendação |
|----------|--------|--------------|
| Binance | 1200 req/min | Max 10 req/seg |
| MEXC | 20 req/seg | Max 15 req/seg |
| Bybit | 120 req/seg | Max 50 req/seg |

O AutoGrid gerencia rate limiting automaticamente.
