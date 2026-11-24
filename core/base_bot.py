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
    def transform(self, files: list[Path]) -> pl.DataFrame:
        """Lee los archivos descargados, limpia columnas y retorna un DataFrame."""
        pass

    @abstractmethod
    def load(self, df: pl.DataFrame) -> int:
        """Sube el DataFrame transformado a SQL Server."""
        pass

    def cleanup(self, files: list[Path]) -> None:
        """Elimina archivos temporales tras una carga exitosa."""
        for f in files:
            if f.exists():
                f.unlink()
                self.log.debug(f"Archivo temporal eliminado: {f.name}")

    async def run(self, keep_files: bool = False) -> None:
        self.log.info(f"Iniciando ejecución | Parámetros: {self.params}")
        files: list[Path] = []
        try:
            files = await self.extract()
            if not files:
                self.log.warning("No se descargaron archivos. Abortando flujo.")
                return

            df = self.transform(files)
            self.load(df)

            if not keep_files:
                self.cleanup(files)

            self.log.success("Ejecución finalizada correctamente.")
        except Exception as e:
            self.log.exception(f"Error crítico durante la ejecución: {e}")
            raise