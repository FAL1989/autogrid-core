---
name: security-checklist
description: Validação de segurança antes de deploy ou go-live. Use quando o usuário quiser revisar segurança, preparar para produção, ou auditar configurações de segurança.
allowed-tools: Read, Grep, Glob
---

# Checklist de Segurança

## Antes de Ir para Produção

### 1. API Keys e Credenciais

- [ ] **Nenhuma API key em código fonte**
  ```bash
  # Verificar
  grep -r "api_key\|api_secret" --include="*.py" --include="*.ts" .
  ```

- [ ] **Variáveis de ambiente para secrets**
  ```bash
  # Correto
  ENCRYPTION_KEY=xxx
  DATABASE_URL=xxx

  # Nunca em código
  api_key = "abc123"  # ERRADO
  ```

- [ ] **API keys sem permissão de withdraw**
  ```python
  # Validação obrigatória
  if credentials.has_withdraw_permission:
      raise SecurityError("Withdraw permission not allowed")
  ```

- [ ] **Criptografia AES-256-GCM para keys armazenadas**

### 2. Autenticação

- [ ] **Senhas com bcrypt** (cost factor ≥ 12)
- [ ] **JWT com expiração curta** (24h access, 7d refresh)
- [ ] **Rate limiting por IP e usuário**
  - Login: 5 tentativas/minuto
  - API: 100 requests/minuto
- [ ] **HTTPS obrigatório** (redirect HTTP → HTTPS)

### 3. Kill Switch Configurado

- [ ] **Max ordens/minuto**: 50
- [ ] **Max perda/hora**: 5% do investimento
- [ ] **Sanity check de preço**: Rejeitar >10% do mercado
- [ ] **Notificação ao disparar**: Email + Telegram

### 4. Database

- [ ] **Não expor PostgreSQL publicamente**
- [ ] **Usuário de app com permissões mínimas**
- [ ] **Backups automáticos diários**
- [ ] **Conexões SSL obrigatórias**

### 5. Infraestrutura

- [ ] **Firewall configurado**
  - Apenas portas 80, 443, 22 (SSH)
  - PostgreSQL/Redis: apenas interno

- [ ] **SSH com chave, não senha**
- [ ] **Fail2ban ativo**
- [ ] **Updates de segurança automáticos**

### 6. Código

- [ ] **Sem SQL injection**
  ```python
  # Correto
  cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))

  # ERRADO
  cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
  ```

- [ ] **Input validation em todos endpoints**
- [ ] **Sem XSS no frontend**
- [ ] **CORS restrito**
  ```python
  ALLOWED_ORIGINS = ["https://autogrid.com"]
  ```

### 7. Logging

- [ ] **Nunca logar API keys**
- [ ] **Nunca logar senhas**
- [ ] **Nunca logar tokens JWT completos**
- [ ] **Logs estruturados (JSON)**
- [ ] **Retenção de logs: 30 dias**

### 8. Monitoramento

- [ ] **Alertas para erros 5xx**
- [ ] **Alertas para falhas de bot**
- [ ] **Alertas para tentativas de login suspeitas**
- [ ] **Dashboard de métricas**

## Verificação Automatizada

```bash
# Rodar antes de cada deploy
autogrid security-check

# Output esperado:
# ✓ No hardcoded credentials found
# ✓ All API keys encrypted
# ✓ Kill switch configured
# ✓ Rate limiting active
# ✓ HTTPS enforced
# ✓ Database not exposed
# ✓ Backups configured
```

## Resposta a Incidentes

### Se API Key Vazou
1. Revogar imediatamente na exchange
2. Gerar nova key
3. Atualizar no sistema
4. Auditar logs para uso não autorizado

### Se Detectar Acesso Não Autorizado
1. Bloquear IP suspeito
2. Forçar logout de todas as sessões
3. Notificar usuários afetados
4. Analisar logs para determinar escopo

### Se Bot Executar Errado
1. Kill switch manual: `autogrid bot stop --all`
2. Cancelar todas ordens abertas
3. Verificar saldo e posições
4. Analisar logs antes de reiniciar

## Compliance

- [ ] Terms of Service claros
- [ ] Disclaimer: "Não é conselho financeiro"
- [ ] GDPR compliance (se aplicável)
- [ ] Política de privacidade
