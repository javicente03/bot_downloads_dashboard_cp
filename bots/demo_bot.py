from pathlib import Path
import polars as pl
from core.base_bot import BaseBot
from core.browser import BrowserManager
from core.database import SQLServerManager


class DemoBot(BaseBot):
    name = "demo"
    description = "Robot de prueba para validar Playwright, Polars y parámetros"

    async def extract(self) -> list[Path]:
        fecha = self.params.get("fecha", "sin_fecha")
        self.log.info(f"Simulando extracción con parámetro fecha={fecha}...")

        async with BrowserManager.get_page() as page:
            await page.goto("https://example.com")
            title = await page.title()
            self.log.info(f"Título obtenido con Playwright: {title}")

        # Creamos un CSV dummy para probar transform y load
        dummy_file = self.download_dir / f"test_{fecha}.csv"
        dummy_file.write_text("id,descripcion,valor\n1,Prueba A,100.5\n2,Prueba B,250.0\n", encoding="utf-8")
        return [dummy_file]

    def transform(self, files: list[Path]) -> pl.DataFrame:
        self.log.info(f"Procesando archivo: {files[0].name}")
        df = pl.read_csv(files[0])
        # Ejemplo de transformación con Polars
        df = df.with_columns(
            pl.lit(self.params.get("fecha", "2026-01-01")).alias("fecha_proceso")
        )
        return df

    def load(self, df: pl.DataFrame) -> int:
        self.log.info(f"DataFrame listo para SQL Server:\n{df}")
        # Descomenta la siguiente línea cuando tengas tu tabla real configurada en .env:
        # return SQLServerManager.insert_dataframe(df, table_name="tabla_demo")
        return df.height