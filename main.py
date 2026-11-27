import asyncio
from datetime import datetime, timedelta
import time
import typer
from rich.console import Console
from rich.table import Table
from bots import BOT_REGISTRY
from config.settings import settings
from core.base_bot import BotPartialError
from core.database import SQLServerManager
from core.notifier import SMTPNotifier

app = typer.Typer(help="Orquestador de Robots de Scraping hacia SQL Server")
console = Console()


def parse_extra_params(params: list[str]) -> dict[str, str]:
    """Convierte argumentos tipo 'clave=valor' en un diccionario."""
    parsed = {}
    for item in params:
        if "=" not in item:
            raise typer.BadParameter(f"El parámetro '{item}' debe tener el formato clave=valor")
        key, value = item.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def _resolve_target_bots(bot: str) -> list[str]:
    if bot == "todos":
        return list(BOT_REGISTRY.keys())
    if bot not in BOT_REGISTRY:
        console.print(f"[bold red]Error:[/bold red] El robot '{bot}' no existe. Usa 'python main.py list'.")
        raise typer.Exit(code=1)
    return [bot]


def _build_bot_params(
    bot_name: str,
    fecha_iso: str,
    sede_val: str,
    reporte_val: str,
    headless: str,
) -> dict[str, str]:
    params: dict[str, str] = {"fecha": fecha_iso, "headless": headless}
    if bot_name in ("amano_japon", "amano_europa") and sede_val not in ("todas", bot_name):
        params["sede"] = sede_val
    if reporte_val != "todos":
        params["reporte"] = reporte_val
    return params


def _optimize_pending_tasks(
    pending_items: list[tuple[str, str, str, str]],
) -> list[tuple[str, str, str, str]]:
    """
    Agrupa combinaciones pendientes (fecha_iso, bot_name, sede, reporte) para evitar
    abrir múltiples navegadores innecesarios en un mismo día/sede.
    """
    expected_by_bot: dict[str, set[tuple[str, str]]] = {}
    expected_by_bot_sede: dict[tuple[str, str], set[str]] = {}
    for b_name, s_name, r_name in settings.expected_pipeline_matrix:
        expected_by_bot.setdefault(b_name, set()).add((s_name, r_name))
        expected_by_bot_sede.setdefault((b_name, s_name), set()).add(r_name)

    grouped_day_bot: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for fecha_iso, bot_name, sede, reporte in pending_items:
        grouped_day_bot.setdefault((fecha_iso, bot_name), set()).add((sede, reporte))

    optimized: list[tuple[str, str, str, str]] = []
    for (fecha_iso, bot_name), pairs in sorted(grouped_day_bot.items()):
        if pairs == expected_by_bot.get(bot_name, set()):
            optimized.append((fecha_iso, bot_name, "todas", "todos"))
            continue

        by_sede: dict[str, set[str]] = {}
        for s_name, r_name in pairs:
            by_sede.setdefault(s_name, set()).add(r_name)

        for s_name, reps in sorted(by_sede.items()):
            if reps == expected_by_bot_sede.get((bot_name, s_name), set()):
                optimized.append((fecha_iso, bot_name, s_name, "todos"))
            else:
                for r_name in sorted(reps):
                    optimized.append((fecha_iso, bot_name, s_name, r_name))

    return optimized


@app.command("list")
def list_bots():
    """Muestra todos los robots registrados y disponibles."""
    table = Table(title="Robots Disponibles")
    table.add_column("Nombre (--bot)", style="cyan", no_wrap=True)
    table.add_column("Descripción", style="white")

    for name, bot_cls in BOT_REGISTRY.items():
        table.add_row(name, bot_cls.description)

    console.print(table)


@app.command("run")
def run_bot(
    bot: str = typer.Option(..., "--bot", "-b", help="Nombre del robot a ejecutar"),
    param: list[str] = typer.Option(
        [],
        "--param",
        "-p",
        help="Parámetros dinámicos en formato clave=valor (puede repetirse)",
    ),
    keep_files: bool = typer.Option(
        True,
        "--keep-files/--delete-files",
        help="Conservar o eliminar archivos descargados tras subir a SQL Server",
    ),
):
    """Ejecuta un robot específico pasándole parámetros opcionales."""
    if bot not in BOT_REGISTRY:
        console.print(f"[bold red]Error:[/bold red] El robot '{bot}' no existe. Usa 'python main.py list'.")
        raise typer.Exit(code=1)

    parsed_params = parse_extra_params(param)
    bot_instance = BOT_REGISTRY[bot](params=parsed_params)
    asyncio.run(bot_instance.run(keep_files=keep_files))


@app.command("auto-sync")
def auto_sync(
    bot: str = typer.Option("todos", "--bot", "-b", help="Robot específico o 'todos'"),
    lookback_days: int = typer.Option(
        settings.AUTO_RETRY_LOOKBACK_DAYS,
        "--lookback-days",
        "-d",
        help="Días hacia atrás desde ayer a auditar y sincronizar (incluye ayer)",
    ),
    headless: str = typer.Option("true", "--headless", help="true o false"),
    delay: float = typer.Option(2.0, "--delay", help="Segundos de pausa entre ejecuciones"),
    keep_files: bool = typer.Option(True, "--keep-files/--delete-files"),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Muestra qué fechas/sedes/reportes están pendientes sin ejecutar los bots",
    ),
    notify: bool = typer.Option(
        True,
        "--notify/--no-notify",
        help="Enviar informe por correo SMTP al finalizar la ejecución",
    ),
):
    """
    Comando diario inteligente: procesa ayer y reprocesa automáticamente cualquier
    día/sede/reporte en ERROR o no ejecutado dentro de la ventana lookback_days.
    """
    if lookback_days < 1:
        raise typer.BadParameter("--lookback-days debe ser mayor o igual a 1")

    started_at = time.monotonic()
    target_bots = set(_resolve_target_bots(bot))
    yesterday = datetime.now().date() - timedelta(days=1)
    start_day = yesterday - timedelta(days=lookback_days - 1)

    start_iso = start_day.isoformat()
    end_iso = yesterday.isoformat()

    SQLServerManager.check_connection()
    completed_keys, latest_map = SQLServerManager.get_completed_keys(
        start_date=start_iso,
        end_date=end_iso,
        bot_name=None if bot == "todos" else bot,
    )

    total_expected = 0
    pending_items: list[tuple[str, str, str, str]] = []
    for offset in range(lookback_days):
        day_iso = (start_day + timedelta(days=offset)).isoformat()
        for b_name, s_name, r_name in settings.expected_pipeline_matrix:
            if b_name not in target_bots:
                continue
            total_expected += 1
            key = (b_name, s_name, r_name, day_iso)
            if key not in completed_keys:
                pending_items.append((day_iso, b_name, s_name, r_name))

    already_ok_count = total_expected - len(pending_items)

    if not pending_items:
        elapsed = time.monotonic() - started_at
        console.print(
            f"[bold green]Todo al día ({start_iso} -> {end_iso}). "
            f"Sin días pendientes ni errores.[/bold green]"
        )
        if notify and not dry_run:
            SMTPNotifier.send_execution_report(
                window_start=start_iso,
                window_end=end_iso,
                total_expected=total_expected,
                already_ok_count=already_ok_count,
                resolved_items=[],
                unresolved_items=[],
                duration_seconds=elapsed,
            )
        return

    table = Table(title=f"Pendientes detectados ({start_iso} -> {end_iso}): {len(pending_items)} reporte(s)")
    table.add_column("Fecha", style="yellow")
    table.add_column("Bot", style="cyan")
    table.add_column("Sede")
    table.add_column("Reporte")
    table.add_column("Motivo", style="magenta")

    for day_iso, b_name, s_name, r_name in pending_items:
        prev = latest_map.get((b_name, s_name, r_name, day_iso))
        if prev:
            reason = f"ERROR previo: {(prev.get('mensaje_error') or '')[:60]}"
        else:
            reason = "SIN EJECUTAR (día nuevo o caído)"
        table.add_row(day_iso, b_name, s_name, r_name, reason)
    console.print(table)

    if dry_run:
        console.print("[bold yellow]Modo --dry-run activo. No se ejecutó ningún robot.[/bold yellow]")
        return

    tasks = _optimize_pending_tasks(pending_items)
    console.print(f"[bold cyan]Ejecutando {len(tasks)} lote(s) optimizado(s)...[/bold cyan]")

    for idx, (day_iso, bot_name, sede_val, reporte_val) in enumerate(tasks, start=1):
        console.rule(
            f"[bold]Lote {idx}/{len(tasks)} — {day_iso} | {bot_name} | sede={sede_val} | reporte={reporte_val}[/bold]"
        )
        params = _build_bot_params(bot_name, day_iso, sede_val, reporte_val, headless)
        try:
            bot_instance = BOT_REGISTRY[bot_name](params=params)
            asyncio.run(bot_instance.run(keep_files=keep_files))
        except BotPartialError as p_exc:
            console.print(f"[bold yellow]Ejecución con errores parciales:[/bold yellow] {p_exc}")
        except Exception as exc:
            console.print(f"[bold red]Fallo en {bot_name} ({day_iso}):[/bold red] {exc}")

        if idx < len(tasks) and delay > 0:
            time.sleep(delay)

    # Auditoría post-ejecución para armar el informe completo
    completed_after, latest_after = SQLServerManager.get_completed_keys(
        start_date=start_iso,
        end_date=end_iso,
        bot_name=None if bot == "todos" else bot,
    )

    resolved_items: list[dict[str, object]] = []
    unresolved_items: list[dict[str, str]] = []

    for day_iso, b_name, s_name, r_name in pending_items:
        key = (b_name, s_name, r_name, day_iso)
        row_info = latest_after.get(key) or {}
        if key in completed_after:
            resolved_items.append({
                "fecha_reporte": day_iso,
                "bot_name": b_name,
                "sede": s_name,
                "reporte": r_name,
                "estado": row_info.get("estado") or "OK",
                "filas_insertadas": row_info.get("filas_insertadas") or 0,
            })
        else:
            unresolved_items.append({
                "fecha_reporte": day_iso,
                "bot_name": b_name,
                "sede": s_name,
                "reporte": r_name,
                "mensaje_error": row_info.get("mensaje_error") or "No se completó la descarga/carga",
            })

    elapsed = time.monotonic() - started_at
    console.rule("[bold green]Resumen Auto-Sync[/bold green]")
    console.print(
        f"Pendientes iniciales: {len(pending_items)} | "
        f"Resueltos: [green]{len(resolved_items)}[/green] | "
        f"Aún pendientes: [red]{len(unresolved_items)}[/red] | "
        f"Tiempo: {elapsed:.1f}s"
    )

    if notify:
        SMTPNotifier.send_execution_report(
            window_start=start_iso,
            window_end=end_iso,
            total_expected=total_expected,
            already_ok_count=already_ok_count,
            resolved_items=resolved_items,
            unresolved_items=unresolved_items,
            duration_seconds=elapsed,
        )

    if unresolved_items:
        raise typer.Exit(code=1)


@app.command("backfill")
def backfill_range(
    bot: str = typer.Option("todos", "--bot", "-b", help="Robot específico o 'todos'"),
    desde: str = typer.Option(..., "--desde", help="Fecha inicial YYYY-MM-DD (inclusive)"),
    hasta: str = typer.Option(..., "--hasta", help="Fecha final YYYY-MM-DD (inclusive)"),
    sede: str = typer.Option("todas", "--sede", help="Filtrar por sede específica (opcional)"),
    reporte: str = typer.Option("todos", "--reporte", help="Filtrar por reporte específico (opcional)"),
    headless: str = typer.Option("true", "--headless", help="true o false"),
    delay: float = typer.Option(2.0, "--delay", help="Segundos de pausa entre cada día"),
    skip_completed: bool = typer.Option(
        True,
        "--skip-completed/--force",
        help="Omitir días ya completados (OK o SIN_DATOS) en dbo.bot_ejecuciones",
    ),
    keep_files: bool = typer.Option(True, "--keep-files/--delete-files"),
):
    """Recorre un rango de fechas iterando estrictamente 1 día a la vez."""
    start_dt = datetime.strptime(desde, "%Y-%m-%d").date()
    end_dt = datetime.strptime(hasta, "%Y-%m-%d").date()
    if start_dt > end_dt:
        raise typer.BadParameter("--desde no puede ser mayor que --hasta")

    target_bots = _resolve_target_bots(bot)
    total_days = (end_dt - start_dt).days + 1

    completed_keys: set[tuple[str, str, str, str]] = set()
    if skip_completed:
        SQLServerManager.check_connection()
        completed_keys, _ = SQLServerManager.get_completed_keys(
            start_date=desde,
            end_date=hasta,
            bot_name=None if bot == "todos" else bot,
        )

    expected_by_bot: dict[str, list[tuple[str, str]]] = {}
    for b_name, s_name, r_name in settings.expected_pipeline_matrix:
        expected_by_bot.setdefault(b_name, []).append((s_name, r_name))

    console.print(
        f"[bold cyan]Iniciando Backfill:[/bold cyan] {desde} -> {hasta} ({total_days} días) | "
        f"Bots: {', '.join(target_bots)} | skip_completed={skip_completed}"
    )

    executed_count = 0
    skipped_count = 0
    failed_runs: list[tuple[str, str, str]] = []

    for offset in range(total_days):
        current_day = start_dt + timedelta(days=offset)
        day_iso = current_day.isoformat()
        console.rule(f"[bold]Día {offset + 1}/{total_days} — {day_iso}[/bold]")

        for bot_name in target_bots:
            bot_matrix = expected_by_bot.get(bot_name, [])
            if (
                skip_completed
                and sede == "todas"
                and reporte == "todos"
                and bot_matrix
                and all((bot_name, s, r, day_iso) in completed_keys for s, r in bot_matrix)
            ):
                console.print(f"[dim]Saltando {bot_name} ({day_iso}): todas sus sedes/reportes ya OK/SIN_DATOS.[/dim]")
                skipped_count += 1
                continue

            params = _build_bot_params(bot_name, day_iso, sede, reporte, headless)
            try:
                bot_instance = BOT_REGISTRY[bot_name](params=params)
                asyncio.run(bot_instance.run(keep_files=keep_files))
                executed_count += 1
            except Exception as exc:
                console.print(f"[bold red]Fallo en {bot_name} ({day_iso}):[/bold red] {exc}")
                failed_runs.append((bot_name, day_iso, str(exc)))

        if offset < total_days - 1 and delay > 0:
            time.sleep(delay)

    console.rule("[bold green]Resumen Backfill[/bold green]")
    console.print(f"Ejecuciones lanzadas: {executed_count} | Días omitidos: {skipped_count} | Errores: {len(failed_runs)}")
    if failed_runs:
        for b_name, d_iso, err in failed_runs:
            console.print(f"  [red]- {b_name} | {d_iso}:[/red] {err}")


@app.command("retry-errors")
def retry_errors(
    bot: str = typer.Option("todos", "--bot", "-b", help="Robot específico o 'todos'"),
    dias: int = typer.Option(7, "--dias", help="Ventana de días hacia atrás para buscar errores"),
    fecha: str = typer.Option("", "--fecha", help="Reprocesar errores solo de una fecha YYYY-MM-DD (opcional)"),
    headless: str = typer.Option("true", "--headless", help="true o false"),
    keep_files: bool = typer.Option(True, "--keep-files/--delete-files"),
    notify: bool = typer.Option(True, "--notify/--no-notify", help="Enviar alerta SMTP si vuelven a fallar"),
):
    """Consulta dbo.bot_ejecuciones y reprocesa únicamente los ítems cuyo último estado sea ERROR."""
    if bot != "todos":
        _resolve_target_bots(bot)

    SQLServerManager.check_connection()

    if fecha:
        start_iso = fecha
        end_iso = fecha
    else:
        end_dt = datetime.now().date()
        start_dt = end_dt - timedelta(days=dias)
        start_iso = start_dt.isoformat()
        end_iso = end_dt.isoformat()

    latest_rows = SQLServerManager.get_latest_executions(
        bot_name=None if bot == "todos" else bot,
        start_date=start_iso,
        end_date=end_iso,
    )
    error_rows = [r for r in latest_rows if r["estado"] == "ERROR" and r["bot_name"] in BOT_REGISTRY]

    if not error_rows:
        console.print(f"[bold green]Sin errores pendientes entre {start_iso} y {end_iso}.[/bold green]")
        return

    table = Table(title=f"Errores pendientes a reprocesar ({len(error_rows)})")
    table.add_column("Bot", style="cyan")
    table.add_column("Sede")
    table.add_column("Reporte")
    table.add_column("Fecha", style="yellow")
    table.add_column("Último Error", style="red")
    for r in error_rows:
        table.add_row(r["bot_name"], r["sede"], r["reporte"], r["fecha_reporte"], (r["mensaje_error"] or "")[:80])
    console.print(table)

    tasks: list[tuple[str, str, str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for r in error_rows:
        item = (r["bot_name"], r["sede"], r["reporte"], r["fecha_reporte"])
        if item not in seen:
            seen.add(item)
            tasks.append(item)

    for idx, (bot_name, sede_val, reporte_val, fecha_val) in enumerate(tasks, start=1):
        console.rule(f"[bold yellow]Reintento {idx}/{len(tasks)}: {bot_name} | {sede_val} | {reporte_val} | {fecha_val}[/bold yellow]")
        params = _build_bot_params(bot_name, fecha_val, sede_val, reporte_val, headless)
        try:
            bot_instance = BOT_REGISTRY[bot_name](params=params)
            asyncio.run(bot_instance.run(keep_files=keep_files))
        except Exception as exc:
            console.print(f"[bold red]Reintento fallido ({bot_name} - {fecha_val}):[/bold red] {exc}")

    # Verifica si tras el reintento siguen quedando errores
    after_rows = SQLServerManager.get_latest_executions(
        bot_name=None if bot == "todos" else bot,
        start_date=start_iso,
        end_date=end_iso,
    )
    still_failing = [
        {
            "fecha_reporte": r["fecha_reporte"],
            "bot_name": r["bot_name"],
            "sede": r["sede"],
            "reporte": r["reporte"],
            "mensaje_error": r["mensaje_error"] or "Error persistente",
        }
        for r in after_rows
        if r["estado"] == "ERROR" and r["bot_name"] in BOT_REGISTRY
    ]
    if still_failing and notify:
        SMTPNotifier.send_failure_alert(
            failures=still_failing,
            context_title=f"retry-errors ({start_iso} -> {end_iso})",
        )


if __name__ == "__main__":
    app()