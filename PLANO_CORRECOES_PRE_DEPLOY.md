# Plano de correcoes pre-deploy (AutoGrid)

Objetivo: garantir estabilidade operacional antes do primeiro deploy, cobrindo:
- reidratacao estavel
- deduplicacao de ordens por nivel
- calculo de PnL com taxas
- controle de saldo/NOTIONAL antes de enviar ordens
- reconciliacao consistente de fills

## Diagnostico (checagem na codebase)

- Estado em memoria: o bot depende de `_running_bots` em `bot/tasks.py`.
- Reidratacao existe, mas ocorre dentro de `tick_running_bots` e precisa ser garantida em startup.
- Deduplicacao por nivel: `bot/strategies/grid.py` usa `grid_level`, mas `Order` ORM nao tem `grid_level` e `OrderManager._persist_order` nao grava esse campo.
- PnL: `process_order_fill` grava `Trade` com `realized_pnl` apenas se a exchange envia; taxas sao gravadas mas nao entram no PnL. `reconcile_running_bots_trades` calcula PnL com taxas, mas so quando reconcilia.
- Controle de saldo: `bot/engine.py` ja checa `min_notional` e saldo livre, mas hoje so bloqueia por ordem; nao limita a quantidade de ordens novas pelo saldo disponivel.
- Reconciliacao: existe `reconcile_running_bots_trades` em `bot/tasks.py`, mas precisa padronizar com `process_order_fill`.

## Fase 1 - Reidratacao estavel

**Objetivo:** garantir que qualquer restart do worker reconstrua o estado do bot sem precisar de start manual.

Tarefas:
1) Acionar reidratacao no startup do worker (signal do Celery) e/ou executar uma vez no primeiro tick, com lock para evitar repeticao.
2) Ajustar `_start_bot_async` para modo `rehydrate` nao seedar novas ordens automaticamente.
3) Restaurar estado de estrategia usando dados persistidos (ver Fase 2/3) para evitar reinicio de PnL/posicoes.

Arquivos:
- `bot/tasks.py`
- `bot/engine.py`

Validacao:
- Restart do `celery` sem parar o bot no dashboard.
- Logs mostram reidratacao 1x e `tick_running_bots` com `ticked > 0`.

## Fase 2 - Deduplicacao de ordens por nivel

**Objetivo:** evitar ordens duplicadas no mesmo nivel/preco.

Tarefas:
1) Adicionar `grid_level` no ORM e na tabela `orders`.
2) Persistir `grid_level` no `OrderManager._persist_order` e carregar em `_orm_to_managed`.
3) Adicionar regra de dedupe antes do submit: bloquear se ja existe `open` do mesmo `bot_id`, `side`, `grid_level`.
4) Opcional: indice unico parcial no banco para `open`/`pending`.

Arquivos:
- `api/models/orm.py`
- `bot/order_manager.py`
- `bot/engine.py`
- migracao SQL (db)

Validacao:
- Restart do worker nao cria ordem duplicada no mesmo nivel.
- `get_open_orders` retorna no max 1 por nivel/side.

## Fase 3 - PnL com taxas

**Objetivo:** PnL realista no dashboard e no relatorio.

Tarefas:
1) Atualizar `process_order_fill` para calcular `realized_pnl` quando a exchange nao envia.
2) Usar FIFO de buys para sells (ja existe em `reconcile_running_bots_trades`) e incluir taxas em quote.
3) Persistir `realized_pnl` no `Trade` no momento do fill e atualizar `Bot.realized_pnl`.
4) Garantir que o dashboard usa `Trade.realized_pnl` (via `order_service.get_bot_statistics`).

Arquivos:
- `bot/tasks.py`
- `api/services/order_service.py`

Validacao:
- Trades recentes mostram `realized_pnl` != 0 quando houver lucro/perda.
- Total PnL e Win Rate no dashboard mudam apos fill.

## Fase 4 - Controle de saldo e NOTIONAL (antes do envio)

**Objetivo:** evitar erros de `insufficient balance` e `NOTIONAL` na exchange.

Tarefas:
1) Pre-filtrar `new_orders` por saldo livre para limitar quantidade (USDT para buys, BTC para sells).
2) Ordenar prioridade das ordens (mais perto do preco atual) e inserir somente as que cabem.
3) Usar `min_notional` e `min_qty/step` quando disponivel na exchange.
4) Reduzir spam de log (1 warning por tick).

Arquivos:
- `bot/engine.py`
- `bot/exchange/connector.py`
- `bot/strategies/grid.py`

Validacao:
- Logs mostram `Order blocked by balance` e nao `insufficient balance`.
- Numero de ordens abertas condiz com saldo livre.

## Fase 5 - Reconciliacao consistente de fills

**Objetivo:** garantir que o estado interno e o DB convergem com a exchange.

Tarefas:
1) Unificar logica de `process_order_fill` com `reconcile_running_bots_trades`.
2) Atualizar orders para `filled`/`cancelled` baseado em trade real da exchange.
3) Corrigir duplicidade `trade_exists` usando `exchange_trade_id` e janela de tempo.
4) Rodar reconciliacao em intervalos menores apos restart e sempre que houver erro de websocket.

Arquivos:
- `bot/tasks.py`
- `bot/order_manager.py`

Validacao:
- `reconcile_running_bots_trades` preenche trades faltantes.
- Ordem e trade ficam consistentes no DB.

## Fase 6 - Validacoes e testes

**Objetivo:** garantir confianca antes do deploy.

Tarefas:
1) Teste de reidratacao: restart do worker com bot `running`.
2) Teste de dedupe: criar 2 ticks e validar 1 ordem por nivel.
3) Teste de PnL: simular buy+sell com fee e conferir `realized_pnl`.
4) Teste de saldo: saldo livre baixo deve bloquear novas ordens.
5) Teste de reconciliacao: apagar trade local e recuperar via exchange.

Saidas esperadas:
- Sem duplicacao de ordens
- Sem `insufficient balance`/`NOTIONAL` em produção
- PnL com taxas refletido no dashboard
- Reidratar nao muda estado/posicao

## Sequencia recomendada

1) Fase 1 (reidratacao) + Fase 2 (dedupe)
2) Fase 3 (PnL com taxas)
3) Fase 4 (saldo/NOTIONAL por lote)
4) Fase 5 (reconciliacao)
5) Fase 6 (testes)

## Criterio de aceite pre-deploy

- Bot reinicia sem perder estado
- Sem ordens duplicadas por nivel
- PnL e Win Rate corretos com taxa
- Nenhum erro de saldo/NOTIONAL nos logs
- Reconciliacao recupera trades ausentes
