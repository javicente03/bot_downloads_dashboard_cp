from pathlib import Path
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Page, Download
from config.settings import settings
from core.logger import get_logger
from datetime import datetime

log = get_logger("BROWSER")

class BrowserManager:
    @staticmethod
    @asynccontextmanager
    async def get_page(headless: bool | None = None):
        is_headless = settings.HEADLESS if headless is None else headless
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=is_headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            context = await browser.new_context(
                accept_downloads=True,
                ignore_https_errors=True,  # Omite advertencias SSL en redes LAN
                viewport={"width": 1366, "height": 768},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()
            page.set_default_timeout(settings.DOWNLOAD_TIMEOUT_MS)
            try:
                yield page
            finally:
                await context.close()
                await browser.close()

    @staticmethod
    async def save_download(download: Download, target_dir: Path, custom_name: str | None = None) -> Path:
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = custom_name or download.suggested_filename
        destination = target_dir / filename

        try:
            await download.save_as(destination)
        except PermissionError:
            stamp = datetime.now().strftime("%H%M%S")
            destination = target_dir / f"{destination.stem}_{stamp}{destination.suffix}"
            log.warning(
                f"Archivo destino bloqueado (posiblemente abierto en Excel). "
                f"Guardando como: {destination.name}"
            )
            await download.save_as(destination)

        log.info(f"Archivo descargado en: {destination}")
        return destination