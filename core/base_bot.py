from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
import polars as pl
from config.settings import settings
from core.logger import get_logger


class BotPartialError(RuntimeError):
    """Indica que el robot finalizó su ciclo pero uno o más reportes/sedes fallaron."""

    def __init__(self, bot_name: str, errors: list[dict[str, str]]):
        self.bot_name = bot_name
        self.errors = errors
        summary = "; ".join(
            f"{e.get('sede')}/{e.get('reporte')} ({e.get('fecha_reporte')}): {e.get('mensaje_error')}"
            for e in errors
        )
        super().__init__(f"[{bot_name}] {len(errors)} error(es) durante la ejecución: {summary}")


class BaseBot(ABC):
    name: str = "base_bot"
    description: str = "Robot base"

    def __init__(self, params: dict[str, Any] | None = None):
        self.params = params or {}
        self.log = get_logger(self.name.upper())
        self.download_dir: Path = settings.DOWNLOADS_DIR / self.name
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.errors: list[dict[str, str]] = []

    def record_error(self, sede: str, reporte: str, fecha_reporte: str, mensaje_error: str) -> None:
        self.errors.append({
            "bot_name": self.name,
            "sede": sede,
            "reporte": reporte,
            "fecha_reporte": fecha_reporte,
            "mensaje_error": mensaje_error,
        })

    @abstractmethod
    async def extract(self) -> list[Path]:
        """Navega, aplica filtros/parámetros y descarga uno o más archivos."""
        pass

    @abstractmethod
    def transform(self, files: list[Path]) -> list[tuple[str, str, str, pl.DataFrame]]:
        """Lee los archivos descargados y retorna lista de (sede, reporte, fecha_iso, DataFrame)."""
        pass

    @abstractmethod
    def load(self, batches: list[tuple[str, str, str, pl.DataFrame]]) -> int:
        """Sube los DataFrames transformados a SQL Server y retorna total de filas."""
        pass

    def cleanup(self, files: list[Path]) -> None:
        """Elimina archivos temporales si se solicita explícitamente."""
        for f in files:
            if f.exists():
                f.unlink()
                self.log.debug(f"Archivo temporal eliminado: {f.name}")

    async def run(self, keep_files: bool = True) -> None:
        self.errors.clear()
        self.log.info(f"Iniciando ejecución | Parámetros: {self.params}")
        files: list[Path] = []
        try:
            files = await self.extract()
            if files:
                batches = self.transform(files)
                inserted = self.load(batches)
                if not keep_files:
                    self.cleanup(files)
                self.log.success(
                    f"Carga finalizada. Archivos procesados: {len(files)} | "
                    f"Registros cargados: {inserted}."
                )
            elif not self.errors:
                self.log.warning("No se descargaron archivos (todos los reportes sin datos o vacíos).")

            if self.errors:
                raise BotPartialError(self.name, self.errors)
        except BotPartialError:
            raise
        except Exception as e:
            self.log.exception(f"Error crítico durante la ejecución: {e}")
            raise