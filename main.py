import asyncio
import typer
from rich.console import Console
from rich.table import Table
from bots import BOT_REGISTRY

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


if __name__ == "__main__":
    app()