"""AutoGrid CLI application."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import typer

from autogrid_cli.client import ApiClient, ApiError
from autogrid_cli.config import DEFAULT_API_URL, Settings, load_settings
from autogrid_cli.output import print_json, print_kv, print_table

app = typer.Typer(help="AutoGrid CLI")
auth_app = typer.Typer(help="Authentication commands")
bots_app = typer.Typer(help="Manage bots")
orders_app = typer.Typer(help="View and manage orders")
trades_app = typer.Typer(help="View trades")
credentials_app = typer.Typer(help="Manage exchange credentials")
backtest_app = typer.Typer(help="Run and inspect backtests")
telegram_app = typer.Typer(help="Telegram link management")
config_app = typer.Typer(help="Local CLI configuration")
reports_app = typer.Typer(help="Reporting commands")

app.add_typer(auth_app, name="auth")
app.add_typer(bots_app, name="bots")
app.add_typer(orders_app, name="orders")
app.add_typer(trades_app, name="trades")
app.add_typer(credentials_app, name="credentials")
app.add_typer(backtest_app, name="backtest")
app.add_typer(telegram_app, name="telegram")
app.add_typer(config_app, name="config")
app.add_typer(reports_app, name="reports")


@app.callback()
def main(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
    api_url: str | None = typer.Option(
        None, "--api-url", help="Override API URL for this run"
    ),
) -> None:
    """Load CLI configuration and initialize context."""
    ctx.obj = load_settings(api_url, json_output)


def _require_auth(settings: Settings) -> None:
    if not settings.access_token:
        typer.secho(
            "Not authenticated. Run `autogrid auth login` first.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)


def _handle_api_error(exc: ApiError) -> None:
    typer.secho(
        f"API error ({exc.status_code}): {exc.detail}",
        fg=typer.colors.RED,
        err=True,
    )
    raise typer.Exit(code=1)


def _load_json_payload(
    config: str | None, config_file: Path | None
) -> dict[str, Any] | None:
    if config and config_file:
        typer.secho(
            "Use either --config or --config-file, not both.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    if config_file:
        try:
            raw = config_file.read_text()
        except OSError as exc:
            typer.secho(f"Failed to read {config_file}: {exc}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
    elif config:
        raw = config
    else:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        typer.secho(f"Invalid JSON: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    if not isinstance(payload, dict):
        typer.secho("Config JSON must be an object.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    return payload


@auth_app.command("login")
def auth_login(
    ctx: typer.Context,
    email: str = typer.Option(None, prompt=True),
    password: str = typer.Option(None, prompt=True, hide_input=True),
) -> None:
    settings: Settings = ctx.obj
    payload = {"email": email, "password": password}
    try:
        with ApiClient(settings) as client:
            data = client.request("POST", "/auth/login", json_body=payload)
    except ApiError as exc:
        _handle_api_error(exc)
    settings.store.set_api_url(settings.api_url)
    settings.store.set_tokens(data["access_token"], data["refresh_token"])
    settings.store.save()
    if settings.json_output:
        print_json({"user_id": data["user_id"], "saved": True})
    else:
        typer.echo("Login successful. Tokens saved to config.")


@auth_app.command("status")
def auth_status(ctx: typer.Context) -> None:
    settings: Settings = ctx.obj
    _require_auth(settings)
    try:
        with ApiClient(settings) as client:
            data = client.request("GET", "/auth/me")
    except ApiError as exc:
        _handle_api_error(exc)
    if settings.json_output:
        print_json(data)
        return
    print_kv(
        "User",
        [
            ("ID", data.get("id")),
            ("Email", data.get("email")),
            ("Plan", data.get("plan")),
            ("Telegram Chat ID", data.get("telegram_chat_id")),
            ("Created At", data.get("created_at")),
        ],
    )


@auth_app.command("logout")
def auth_logout(ctx: typer.Context) -> None:
    settings: Settings = ctx.obj
    settings.store.clear_tokens()
    settings.store.save()
    if settings.json_output:
        print_json({"logged_out": True})
    else:
        typer.echo("Logged out. Tokens cleared from config.")


@config_app.command("get")
def config_get(
    ctx: typer.Context,
    key: str = typer.Argument("api-url", help="Config key to read"),
) -> None:
    settings: Settings = ctx.obj
    if key != "api-url":
        typer.secho("Only api-url is supported.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    api_url = settings.store.get("api", "url") or DEFAULT_API_URL
    if settings.json_output:
        print_json({"api_url": api_url})
    else:
        typer.echo(api_url)


@config_app.command("set")
def config_set(
    ctx: typer.Context,
    key: str = typer.Argument(..., help="Config key to set"),
    value: str = typer.Argument(..., help="Value to set"),
) -> None:
    settings: Settings = ctx.obj
    if key != "api-url":
        typer.secho("Only api-url is supported.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    settings.store.set_api_url(value)
    settings.store.save()
    if settings.json_output:
        print_json({"api_url": value})
    else:
        typer.echo("API URL saved.")


@bots_app.command("list")
def bots_list(
    ctx: typer.Context,
    limit: int = typer.Option(50, help="Max bots to return"),
    offset: int = typer.Option(0, help="Pagination offset"),
) -> None:
    settings: Settings = ctx.obj
    _require_auth(settings)
    params = {"limit": limit, "offset": offset}
    try:
        with ApiClient(settings) as client:
            data = client.request("GET", "/api/v1/bots", params=params)
    except ApiError as exc:
        _handle_api_error(exc)
    if settings.json_output:
        print_json(data)
        return
    rows = [
        (
            bot["id"],
            bot["name"],
            bot["strategy"],
            bot["symbol"],
            bot["status"],
            bot["realized_pnl"],
            bot["unrealized_pnl"],
            bot["updated_at"],
        )
        for bot in data.get("bots", [])
    ]
    print_table(
        ["ID", "Name", "Strategy", "Symbol", "Status", "Realized", "Unrealized", "Updated"],
        rows,
        title="Bots",
    )


@bots_app.command("get")
def bots_get(ctx: typer.Context, bot_id: str = typer.Argument(...)) -> None:
    settings: Settings = ctx.obj
    _require_auth(settings)
    try:
        with ApiClient(settings) as client:
            data = client.request("GET", f"/api/v1/bots/{bot_id}")
    except ApiError as exc:
        _handle_api_error(exc)
    if settings.json_output:
        print_json(data)
        return
    print_kv(
        "Bot",
        [
            ("ID", data.get("id")),
            ("Name", data.get("name")),
            ("Strategy", data.get("strategy")),
            ("Exchange", data.get("exchange")),
            ("Symbol", data.get("symbol")),
            ("Status", data.get("status")),
            ("Realized PnL", data.get("realized_pnl")),
            ("Unrealized PnL", data.get("unrealized_pnl")),
            ("Created At", data.get("created_at")),
            ("Updated At", data.get("updated_at")),
        ],
    )


@bots_app.command("create")
def bots_create(
    ctx: typer.Context,
    name: str = typer.Option(..., help="Bot name"),
    credential_id: str = typer.Option(..., help="Credential UUID"),
    strategy: str = typer.Option(..., help="grid or dca"),
    symbol: str = typer.Option(..., help="Trading pair, e.g. BTC/USDT"),
    lower_price: float | None = typer.Option(None, help="Grid lower price"),
    upper_price: float | None = typer.Option(None, help="Grid upper price"),
    grid_count: int | None = typer.Option(None, help="Grid count"),
    investment: float | None = typer.Option(None, help="Total investment"),
    amount: float | None = typer.Option(None, help="DCA amount per buy"),
    interval: str | None = typer.Option(None, help="DCA interval"),
    trigger_drop: float | None = typer.Option(None, help="DCA trigger drop %"),
    take_profit: float | None = typer.Option(None, help="DCA take profit %"),
) -> None:
    settings: Settings = ctx.obj
    _require_auth(settings)
    strategy = strategy.lower()
    config: dict[str, Any]
    if strategy == "grid":
        missing = [val is None for val in (lower_price, upper_price, grid_count, investment)]
        if any(missing):
            typer.secho(
                "Grid requires --lower-price, --upper-price, --grid-count, --investment.",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1)
        config = {
            "lower_price": lower_price,
            "upper_price": upper_price,
            "grid_count": grid_count,
            "investment": investment,
        }
    elif strategy == "dca":
        if amount is None or interval is None:
            typer.secho(
                "DCA requires --amount and --interval.",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1)
        config = {
            "amount": amount,
            "interval": interval,
        }
        if trigger_drop is not None:
            config["trigger_drop"] = trigger_drop
        if take_profit is not None:
            config["take_profit"] = take_profit
        if investment is not None:
            config["investment"] = investment
    else:
        typer.secho("Strategy must be grid or dca.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    payload = {
        "name": name,
        "credential_id": credential_id,
        "strategy": strategy,
        "symbol": symbol,
        "config": config,
    }
    try:
        with ApiClient(settings) as client:
            data = client.request("POST", "/api/v1/bots", json_body=payload)
    except ApiError as exc:
        _handle_api_error(exc)
    if settings.json_output:
        print_json(data)
    else:
        typer.echo(f"Bot created: {data.get('id')}")


@bots_app.command("update")
def bots_update(
    ctx: typer.Context,
    bot_id: str = typer.Argument(...),
    name: str | None = typer.Option(None, help="New bot name"),
    config: str | None = typer.Option(None, help="Config JSON"),
    config_file: Path | None = typer.Option(None, help="Path to config JSON file"),
) -> None:
    settings: Settings = ctx.obj
    _require_auth(settings)
    config_payload = _load_json_payload(config, config_file)
    if name is None and config_payload is None:
        typer.secho("Provide --name or --config.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    payload: dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if config_payload is not None:
        payload["config"] = config_payload
    try:
        with ApiClient(settings) as client:
            data = client.request(
                "PATCH",
                f"/api/v1/bots/{bot_id}",
                json_body=payload,
            )
    except ApiError as exc:
        _handle_api_error(exc)
    if settings.json_output:
        print_json(data)
    else:
        typer.echo("Bot updated.")


@bots_app.command("start")
def bots_start(ctx: typer.Context, bot_id: str = typer.Argument(...)) -> None:
    settings: Settings = ctx.obj
    _require_auth(settings)
    try:
        with ApiClient(settings) as client:
            data = client.request("POST", f"/api/v1/bots/{bot_id}/start")
    except ApiError as exc:
        _handle_api_error(exc)
    if settings.json_output:
        print_json(data)
    else:
        typer.echo(data.get("message", "Start requested."))


@bots_app.command("stop")
def bots_stop(ctx: typer.Context, bot_id: str = typer.Argument(...)) -> None:
    settings: Settings = ctx.obj
    _require_auth(settings)
    try:
        with ApiClient(settings) as client:
            data = client.request("POST", f"/api/v1/bots/{bot_id}/stop")
    except ApiError as exc:
        _handle_api_error(exc)
    if settings.json_output:
        print_json(data)
    else:
        typer.echo(data.get("message", "Stop requested."))


@bots_app.command("delete")
def bots_delete(ctx: typer.Context, bot_id: str = typer.Argument(...)) -> None:
    settings: Settings = ctx.obj
    _require_auth(settings)
    try:
        with ApiClient(settings) as client:
            client.request("DELETE", f"/api/v1/bots/{bot_id}")
    except ApiError as exc:
        _handle_api_error(exc)
    if settings.json_output:
        print_json({"deleted": bot_id})
    else:
        typer.echo("Bot deleted.")


@orders_app.command("list")
def orders_list(
    ctx: typer.Context,
    bot_id: str = typer.Argument(...),
    status: str | None = typer.Option(None, help="Filter by status"),
    limit: int = typer.Option(100, help="Max orders"),
    offset: int = typer.Option(0, help="Pagination offset"),
) -> None:
    settings: Settings = ctx.obj
    _require_auth(settings)
    params = {"limit": limit, "offset": offset}
    if status:
        params["status"] = status
    try:
        with ApiClient(settings) as client:
            data = client.request(
                "GET",
                f"/api/v1/orders/bots/{bot_id}/orders",
                params=params,
            )
    except ApiError as exc:
        _handle_api_error(exc)
    if settings.json_output:
        print_json(data)
        return
    rows = [
        (
            order["id"],
            order["side"],
            order["type"],
            order["price"],
            order["quantity"],
            order["status"],
            order["created_at"],
        )
        for order in data.get("orders", [])
    ]
    print_table(
        ["ID", "Side", "Type", "Price", "Qty", "Status", "Created"],
        rows,
        title="Orders",
    )


@orders_app.command("open")
def orders_open(ctx: typer.Context, bot_id: str = typer.Argument(...)) -> None:
    settings: Settings = ctx.obj
    _require_auth(settings)
    try:
        with ApiClient(settings) as client:
            data = client.request(
                "GET",
                f"/api/v1/orders/bots/{bot_id}/orders/open",
            )
    except ApiError as exc:
        _handle_api_error(exc)
    if settings.json_output:
        print_json(data)
        return
    rows = [
        (
            order["id"],
            order["side"],
            order["price"],
            order["quantity"],
            order["status"],
            order["created_at"],
        )
        for order in data
    ]
    print_table(
        ["ID", "Side", "Price", "Qty", "Status", "Created"],
        rows,
        title="Open Orders",
    )


@orders_app.command("cancel")
def orders_cancel(
    ctx: typer.Context,
    bot_id: str = typer.Argument(...),
    order_id: str = typer.Argument(...),
) -> None:
    settings: Settings = ctx.obj
    _require_auth(settings)
    try:
        with ApiClient(settings) as client:
            data = client.request(
                "POST",
                f"/api/v1/orders/bots/{bot_id}/orders/{order_id}/cancel",
            )
    except ApiError as exc:
        _handle_api_error(exc)
    if settings.json_output:
        print_json(data)
    else:
        typer.echo(data.get("message", "Cancel requested."))


@trades_app.command("list")
def trades_list(
    ctx: typer.Context,
    bot_id: str = typer.Argument(...),
    limit: int = typer.Option(100, help="Max trades"),
    offset: int = typer.Option(0, help="Pagination offset"),
) -> None:
    settings: Settings = ctx.obj
    _require_auth(settings)
    params = {"limit": limit, "offset": offset}
    try:
        with ApiClient(settings) as client:
            data = client.request(
                "GET",
                f"/api/v1/orders/bots/{bot_id}/trades",
                params=params,
            )
    except ApiError as exc:
        _handle_api_error(exc)
    if settings.json_output:
        print_json(data)
        return
    rows = [
        (
            trade["id"],
            trade["side"],
            trade["price"],
            trade["quantity"],
            trade["fee"],
            trade.get("realized_pnl"),
            trade["timestamp"],
        )
        for trade in data.get("trades", [])
    ]
    print_table(
        ["ID", "Side", "Price", "Qty", "Fee", "PnL", "Time"],
        rows,
        title="Trades",
    )


@credentials_app.command("add")
def credentials_add(
    ctx: typer.Context,
    exchange: str = typer.Option(..., help="binance, mexc, or bybit"),
    api_key: str = typer.Option(None, prompt=True),
    api_secret: str = typer.Option(None, prompt=True, hide_input=True),
    testnet: bool = typer.Option(False, "--testnet", help="Use testnet"),
) -> None:
    settings: Settings = ctx.obj
    _require_auth(settings)
    payload = {
        "exchange": exchange.lower(),
        "api_key": api_key,
        "api_secret": api_secret,
        "is_testnet": testnet,
    }
    try:
        with ApiClient(settings) as client:
            data = client.request("POST", "/api/v1/credentials", json_body=payload)
    except ApiError as exc:
        _handle_api_error(exc)
    if settings.json_output:
        print_json(data)
        return
    warnings = data.get("warnings") or []
    credential = data.get("credential", {})
    typer.echo(f"Credential created: {credential.get('id')}")
    for warning in warnings:
        typer.echo(warning)


@credentials_app.command("list")
def credentials_list(
    ctx: typer.Context,
    limit: int = typer.Option(50),
    offset: int = typer.Option(0),
) -> None:
    settings: Settings = ctx.obj
    _require_auth(settings)
    params = {"limit": limit, "offset": offset}
    try:
        with ApiClient(settings) as client:
            data = client.request("GET", "/api/v1/credentials", params=params)
    except ApiError as exc:
        _handle_api_error(exc)
    if settings.json_output:
        print_json(data)
        return
    rows = []
    for cred in data.get("credentials", []):
        permissions = cred.get("permissions", {})
        rows.append(
            (
                cred.get("id"),
                cred.get("exchange"),
                cred.get("is_testnet"),
                permissions.get("trade"),
                permissions.get("withdraw"),
                cred.get("created_at"),
            )
        )
    print_table(
        ["ID", "Exchange", "Testnet", "Trade", "Withdraw", "Created"],
        rows,
        title="Credentials",
    )


@credentials_app.command("delete")
def credentials_delete(ctx: typer.Context, credential_id: str = typer.Argument(...)) -> None:
    settings: Settings = ctx.obj
    _require_auth(settings)
    try:
        with ApiClient(settings) as client:
            client.request("DELETE", f"/api/v1/credentials/{credential_id}")
    except ApiError as exc:
        _handle_api_error(exc)
    if settings.json_output:
        print_json({"deleted": credential_id})
    else:
        typer.echo("Credential deleted.")


@credentials_app.command("test")
def credentials_test(ctx: typer.Context, credential_id: str = typer.Argument(...)) -> None:
    settings: Settings = ctx.obj
    _require_auth(settings)
    try:
        with ApiClient(settings) as client:
            data = client.request(
                "POST", f"/api/v1/credentials/{credential_id}/refresh-markets"
            )
    except ApiError as exc:
        _handle_api_error(exc)
    if settings.json_output:
        print_json(data)
    else:
        typer.echo(f"{data.get('exchange')} markets: {data.get('count')}")


@backtest_app.command("run")
def backtest_run(
    ctx: typer.Context,
    strategy: str = typer.Option(..., help="grid or dca"),
    symbol: str = typer.Option(..., help="Trading pair"),
    timeframe: str = typer.Option(..., help="Timeframe (e.g. 1h)"),
    start_date: str = typer.Option(..., help="YYYY-MM-DD"),
    end_date: str = typer.Option(..., help="YYYY-MM-DD"),
    config: str | None = typer.Option(None, help="Config JSON"),
    config_file: Path | None = typer.Option(None, help="Config JSON file"),
) -> None:
    settings: Settings = ctx.obj
    _require_auth(settings)
    try:
        start_dt = date.fromisoformat(start_date)
        end_dt = date.fromisoformat(end_date)
    except ValueError as exc:
        typer.secho(f"Invalid date: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    config_payload = _load_json_payload(config, config_file)
    if config_payload is None:
        typer.secho("Backtest requires --config.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    payload = {
        "strategy": strategy,
        "symbol": symbol,
        "timeframe": timeframe,
        "start_date": start_dt.isoformat(),
        "end_date": end_dt.isoformat(),
        "config": config_payload,
    }
    try:
        with ApiClient(settings) as client:
            data = client.request("POST", "/api/v1/backtest", json_body=payload)
    except ApiError as exc:
        _handle_api_error(exc)
    if settings.json_output:
        print_json(data)
    else:
        typer.echo(f"Backtest complete: {data.get('id')}")


@backtest_app.command("list")
def backtest_list(
    ctx: typer.Context,
    limit: int = typer.Option(50),
    offset: int = typer.Option(0),
) -> None:
    settings: Settings = ctx.obj
    _require_auth(settings)
    params = {"limit": limit, "offset": offset}
    try:
        with ApiClient(settings) as client:
            data = client.request("GET", "/api/v1/backtest", params=params)
    except ApiError as exc:
        _handle_api_error(exc)
    if settings.json_output:
        print_json(data)
        return
    rows = [
        (
            test["id"],
            test["strategy"],
            test["symbol"],
            test["timeframe"],
            test["status"],
            test.get("total_return"),
            test.get("total_trades"),
            test["created_at"],
        )
        for test in data.get("backtests", [])
    ]
    print_table(
        ["ID", "Strategy", "Symbol", "TF", "Status", "Return", "Trades", "Created"],
        rows,
        title="Backtests",
    )


@backtest_app.command("show")
def backtest_show(ctx: typer.Context, backtest_id: str = typer.Argument(...)) -> None:
    settings: Settings = ctx.obj
    _require_auth(settings)
    try:
        with ApiClient(settings) as client:
            data = client.request("GET", f"/api/v1/backtest/{backtest_id}")
    except ApiError as exc:
        _handle_api_error(exc)
    if settings.json_output:
        print_json(data)
        return
    print_kv(
        "Backtest",
        [
            ("ID", data.get("id")),
            ("Strategy", data.get("strategy")),
            ("Symbol", data.get("symbol")),
            ("Return", data.get("total_return")),
            ("Sharpe", data.get("sharpe_ratio")),
            ("Max Drawdown", data.get("max_drawdown")),
            ("Win Rate", data.get("win_rate")),
            ("Profit Factor", data.get("profit_factor")),
            ("Total Trades", data.get("total_trades")),
        ],
    )


@telegram_app.command("link")
def telegram_link(ctx: typer.Context) -> None:
    settings: Settings = ctx.obj
    _require_auth(settings)
    try:
        with ApiClient(settings) as client:
            data = client.request("POST", "/api/v1/telegram/link")
    except ApiError as exc:
        _handle_api_error(exc)
    if settings.json_output:
        print_json(data)
        return
    print_kv(
        "Telegram Link",
        [
            ("Token", data.get("token")),
            ("Expires At", data.get("expires_at")),
            ("Start Command", data.get("start_command")),
            ("Deep Link", data.get("deep_link")),
        ],
    )


@telegram_app.command("unlink")
def telegram_unlink(ctx: typer.Context) -> None:
    settings: Settings = ctx.obj
    _require_auth(settings)
    try:
        with ApiClient(settings) as client:
            client.request("POST", "/api/v1/telegram/unlink")
    except ApiError as exc:
        _handle_api_error(exc)
    if settings.json_output:
        print_json({"unlinked": True})
    else:
        typer.echo("Telegram unlinked.")


@reports_app.command("bots")
def reports_bots(ctx: typer.Context) -> None:
    settings: Settings = ctx.obj
    _require_auth(settings)
    try:
        with ApiClient(settings) as client:
            data = client.request("GET", "/api/v1/reports/bots")
    except ApiError as exc:
        _handle_api_error(exc)
    if settings.json_output:
        print_json(data)
        return
    rows = [
        (
            bot["bot_id"],
            bot["name"],
            bot["strategy"],
            bot["symbol"],
            bot["status"],
            bot["realized_pnl"],
            bot["unrealized_pnl"],
            bot["total_trades"],
        )
        for bot in data.get("bots", [])
    ]
    print_table(
        ["ID", "Name", "Strategy", "Symbol", "Status", "Realized", "Unrealized", "Trades"],
        rows,
        title="Bot Performance",
    )


@reports_app.command("strategies")
def reports_strategies(ctx: typer.Context) -> None:
    settings: Settings = ctx.obj
    _require_auth(settings)
    try:
        with ApiClient(settings) as client:
            data = client.request("GET", "/api/v1/reports/strategies")
    except ApiError as exc:
        _handle_api_error(exc)
    if settings.json_output:
        print_json(data)
        return
    rows = [
        (
            item["strategy"],
            item["total_bots"],
            item["total_trades"],
            item["win_rate"],
            item["total_pnl"],
            item["total_volume"],
        )
        for item in data.get("strategies", [])
    ]
    print_table(
        ["Strategy", "Bots", "Trades", "Win Rate", "PnL", "Volume"],
        rows,
        title="Strategy Comparison",
    )


@reports_app.command("export")
def reports_export(
    ctx: typer.Context,
    output: Path = typer.Option(Path("trades.csv"), help="Output CSV path"),
    bot_id: str | None = typer.Option(None, help="Filter by bot ID"),
) -> None:
    settings: Settings = ctx.obj
    _require_auth(settings)
    params = {"bot_id": bot_id} if bot_id else None
    try:
        with ApiClient(settings) as client:
            response = client.request_raw(
                "GET", "/api/v1/reports/trades/export", params=params
            )
    except ApiError as exc:
        _handle_api_error(exc)
    try:
        output.write_bytes(response.content)
    except OSError as exc:
        typer.secho(f"Failed to write {output}: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if settings.json_output:
        print_json({"saved": str(output)})
    else:
        typer.echo(f"CSV saved to {output}")
