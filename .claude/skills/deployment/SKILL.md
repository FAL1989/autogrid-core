---
name: deployment
description: Deploy do AutoGrid em produção. Use quando o usuário quiser fazer deploy, configurar servidor, ou migrar para cloud (DigitalOcean).
allowed-tools: Read, Grep, Glob, Bash
---

# Deployment do AutoGrid

## Opções de Deploy

| Modo | Custo | Complexidade | Recomendado para |
|------|-------|--------------|------------------|
| Self-hosted | $0 + servidor | Média | Devs, controle total |
| Docker local | $0 | Baixa | Desenvolvimento, testes |
| DigitalOcean | $50+/mês | Baixa | Produção, escala |

## 1. Deploy Local (Docker)

### Requisitos
- Docker 20.10+
- Docker Compose 2.0+
- 4GB RAM mínimo

### Passos
```bash
# Clone o repositório
git clone https://github.com/autogrid/autogrid.git
cd autogrid

# Configurar variáveis de ambiente
cp .env.example .env
nano .env

# Variáveis obrigatórias:
# ENCRYPTION_KEY=<gerar com: openssl rand -hex 32>
# DATABASE_URL=postgresql://postgres:postgres@postgres:5432/autogrid
# REDIS_URL=redis://redis:6379
# JWT_SECRET=<gerar com: openssl rand -hex 32>

# Subir serviços
docker-compose up -d

# Verificar status
docker-compose ps

# Rodar migrations
docker-compose exec api alembic upgrade head

# Acessar
# API: http://localhost:8000
# Docs: http://localhost:8000/docs
# Web: http://localhost:3000
```

## 2. Deploy DigitalOcean App Platform

### Pré-requisitos
- Conta DigitalOcean
- `doctl` CLI instalado
- Repositório no GitHub

### Passos

```bash
# Login no DO
doctl auth init

# Criar database managed
doctl databases create autogrid-db \
  --engine pg \
  --version 15 \
  --size db-s-1vcpu-1gb \
  --region nyc1

# Criar Redis managed
doctl databases create autogrid-redis \
  --engine redis \
  --version 7 \
  --size db-s-1vcpu-1gb \
  --region nyc1

# Deploy via App Platform
doctl apps create --spec .do/app.yaml
```

### Arquivo `.do/app.yaml`
```yaml
name: autogrid
region: nyc
services:
  - name: api
    github:
      repo: seu-usuario/autogrid
      branch: main
      deploy_on_push: true
    source_dir: /api
    dockerfile_path: Dockerfile
    instance_count: 1
    instance_size_slug: basic-xxs
    envs:
      - key: DATABASE_URL
        scope: RUN_TIME
        value: ${db.DATABASE_URL}
      - key: REDIS_URL
        scope: RUN_TIME
        value: ${redis.REDIS_URL}
      - key: ENCRYPTION_KEY
        scope: RUN_TIME
        type: SECRET

  - name: bot-engine
    github:
      repo: seu-usuario/autogrid
      branch: main
    source_dir: /bot
    dockerfile_path: Dockerfile
    instance_count: 1
    instance_size_slug: basic-xs

  - name: web
    github:
      repo: seu-usuario/autogrid
      branch: main
    source_dir: /web
    build_command: npm run build
    run_command: npm start
    instance_size_slug: basic-xxs

databases:
  - name: db
    engine: PG
    version: "15"
  - name: redis
    engine: REDIS
    version: "7"
```

## 3. Deploy VPS Manual

### Requisitos
- Ubuntu 22.04 LTS
- 2 vCPU, 4GB RAM
- 50GB SSD

### Setup do Servidor

```bash
# Atualizar sistema
sudo apt update && sudo apt upgrade -y

# Instalar Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Instalar Docker Compose
sudo apt install docker-compose-plugin

# Configurar firewall
sudo ufw allow 22
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable

# Instalar Nginx (reverse proxy)
sudo apt install nginx certbot python3-certbot-nginx

# Configurar SSL
sudo certbot --nginx -d autogrid.seudominio.com
```

### Nginx Config
```nginx
# /etc/nginx/sites-available/autogrid
server {
    listen 443 ssl;
    server_name autogrid.seudominio.com;

    ssl_certificate /etc/letsencrypt/live/autogrid.seudominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/autogrid.seudominio.com/privkey.pem;

    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
    }
}
```

## Checklist Pós-Deploy

- [ ] HTTPS funcionando
- [ ] Variáveis de ambiente configuradas
- [ ] Database migrations executadas
- [ ] Backups configurados
- [ ] Monitoramento ativo
- [ ] Logs centralizados
- [ ] Alertas configurados

## Comandos Úteis

```bash
# Ver logs em produção
doctl apps logs <app-id> --follow

# Escalar serviço
doctl apps update <app-id> --spec updated-app.yaml

# Rollback
doctl apps create-deployment <app-id> --force-rebuild
```

## Custos Estimados

| Componente | Custo/mês |
|------------|-----------|
| App Platform (2 services) | $24 |
| Managed PostgreSQL | $15 |
| Managed Redis | $10 |
| **Total inicial** | **~$50** |
