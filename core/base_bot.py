from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
import polars as pl
from config.settings import settings
from core.logger import get_logger


class BaseBot(ABC):
    name: str = "base_bot"
    description: str = "Robot base"

    def __init__(self, params: dict[str, Any] | None = None):
        self.params = params or {}
        self.log = get_logger(self.name.upper())
        self.download_dir: Path = settings.DOWNLOADS_DIR / self.name
        self.download_dir.mkdir(parents=True, exist_ok=True)

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
        self.log.info(f"Iniciando ejecución | Parámetros: {self.params}")
        files: list[Path] = []
        try:
            files = await self.extract()
            if not files:
                self.log.warning("No se descargaron o encontraron archivos. Abortando flujo.")
                return

            batches = self.transform(files)
            inserted = self.load(batches)

            if not keep_files:
                self.cleanup(files)

            self.log.success(
                f"Ejecución finalizada. Archivos procesados: {len(files)} | "
                f"Registros cargados: {inserted}."
            )
        except Exception as e:
            self.log.exception(f"Error crítico durante la ejecución: {e}")
            raise