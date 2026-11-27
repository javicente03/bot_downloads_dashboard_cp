import asyncio
from datetime import datetime, timedelta
import time
import typer
from rich.console import Console
from rich.table import Table
from bots import BOT_REGISTRY
from core.database import SQLServerManager

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
        help="Conservar o eliminar archivos descargados tras subir a SQL Server (por defecto se conservan)",
    ),
):
    """Ejecuta un robot específico pasándole parámetros opcionales."""
    if bot not in BOT_REGISTRY:
        console.print(f"[bold red]Error:[/bold red] El robot '{bot}' no existe. Usa 'python main.py list'.")
        raise typer.Exit(code=1)

    parsed_params = parse_extra_params(param)
    bot_instance = BOT_REGISTRY[bot](params=parsed_params)
    asyncio.run(bot_instance.run(keep_files=keep_files))


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

    completed_index: set[tuple[str, str]] = set()
    if skip_completed:
        SQLServerManager.check_connection()
        latest_rows = SQLServerManager.get_latest_executions(
            bot_name=None if bot == "todos" else bot,
            start_date=desde,
            end_date=hasta,
        )
        # Agrupa por (bot_name, fecha_reporte) si no tiene ningún ERROR pendiente
        by_bot_date: dict[tuple[str, str], list[str]] = {}
        for row in latest_rows:
            key = (row["bot_name"], row["fecha_reporte"])
            by_bot_date.setdefault(key, []).append(row["estado"])

        for key, states in by_bot_date.items():
            if states and all(st in ("OK", "SIN_DATOS") for st in states):
                completed_index.add(key)

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
            if skip_completed and sede == "todas" and reporte == "todos" and (bot_name, day_iso) in completed_index:
                console.print(f"[dim]Saltando {bot_name} ({day_iso}): ya registrado como OK/SIN_DATOS.[/dim]")
                skipped_count += 1
                continue

            params: dict[str, str] = {"fecha": day_iso, "headless": headless}
            if sede != "todas" and bot_name in ("amano_japon", "amano_europa"):
                params["sede"] = sede
            if reporte != "todos":
                params["reporte"] = reporte

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

    # Deduplica combinaciones (bot_name, sede, reporte, fecha_reporte)
    tasks: list[tuple[str, str, str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for r in error_rows:
        item = (r["bot_name"], r["sede"], r["reporte"], r["fecha_reporte"])
        if item not in seen:
            seen.add(item)
            tasks.append(item)

    for idx, (bot_name, sede_val, reporte_val, fecha_val) in enumerate(tasks, start=1):
        console.rule(f"[bold yellow]Reintento {idx}/{len(tasks)}: {bot_name} | {sede_val} | {reporte_val} | {fecha_val}[/bold yellow]")
        params: dict[str, str] = {"fecha": fecha_val, "headless": headless}
        if bot_name in ("amano_japon", "amano_europa") and sede_val not in ("todas", bot_name):
            params["sede"] = sede_val
        if reporte_val != "todos":
            params["reporte"] = reporte_val

        try:
            bot_instance = BOT_REGISTRY[bot_name](params=params)
            asyncio.run(bot_instance.run(keep_files=keep_files))
        except Exception as exc:
            console.print(f"[bold red]Reintento fallido ({bot_name} - {fecha_val}):[/bold red] {exc}")


if __name__ == "__main__":
    app()