import asyncio
from datetime import date, datetime, time as dt_time, timedelta
import math
from pathlib import Path
import re
import time
import unicodedata
import openpyxl
import polars as pl
from playwright.async_api import Locator, Page
from config.settings import settings
from core.base_bot import BaseBot
from core.browser import BrowserManager
from core.database import SQLServerManager


REPORTS_CONFIG: dict[str, dict[str, str]] = {
    "pagos": {
        "label": "Pagos (Exitosos)",
        "path": "/pagos",
        "payment_status": "payment_successful",
        "expected_type": "pago",
        "table": "redcomercio_cps_pagos",
    },
    "transacciones": {
        "label": "Transacciones",
        "path": "/transacciones",
        "payment_status": "",
        "expected_type": "transacci",
        "table": "redcomercio_cps_transacciones",
    },
}


def _norm_header(text_val: str) -> str:
    """Normaliza cabeceras ignorando tildes y mayúsculas ('Cupón Descuento' -> 'cupon descuento')."""
    clean = unicodedata.normalize("NFKD", str(text_val)).encode("ascii", "ignore").decode("ascii")
    return " ".join(clean.lower().strip().split())


PAGOS_HEADER_MAP: dict[str, str] = {
    _norm_header("ID"): "pago_id",
    _norm_header("ID transacción"): "transaccion_id",
    _norm_header("Empresa"): "empresa",
    _norm_header("Sucursal"): "sucursal",
    _norm_header("Calza"): "calza",
    _norm_header("Patente"): "patente",
    _norm_header("Operador"): "operador",
    _norm_header("Dispositivo"): "dispositivo",
    _norm_header("Host"): "host",
    _norm_header("Minutos"): "minutos",
    _norm_header("Subtotal"): "subtotal",
    _norm_header("Redondeo"): "redondeo",
    _norm_header("Descuento"): "descuento",
    _norm_header("Monto"): "monto",
    _norm_header("Nombre Descuento"): "nombre_descuento",
    _norm_header("Cupón Descuento"): "cupon_descuento",
    _norm_header("Fecha Creación"): "fecha_creacion",
    _norm_header("Fecha de Exito/Rechazo"): "fecha_exito_rechazo",
    _norm_header("Folio"): "folio",
    _norm_header("Estado"): "estado",
    _norm_header("Estado en SII"): "estado_sii",
    _norm_header("Medio de pago"): "medio_pago",
    _norm_header("Tipo Tarjeta"): "tipo_tarjeta",
    _norm_header("Nro Tarjeta"): "nro_tarjeta",
    _norm_header("Servicio"): "servicio",
    _norm_header("Tipo de Cobro"): "tipo_cobro",
    _norm_header("Código de Autorización"): "codigo_autorizacion",
    _norm_header("Nro Operación"): "nro_operacion",
    _norm_header("Confirmación"): "confirmacion",
    _norm_header("Descripción"): "descripcion",
    _norm_header("RUT Suscripción"): "rut_suscripcion",
    _norm_header("URL"): "url",
    _norm_header("Voucher Url"): "voucher_url",
    _norm_header("Recarga Sonda - ID Tarjeta"): "recarga_sonda_id_tarjeta",
    _norm_header("Recarga Sonda - ID Transacción Carga"): "recarga_sonda_id_tx_carga",
    _norm_header("Recarga Sonda - Anulada"): "recarga_sonda_anulada",
    _norm_header("Recarga Sonda - ID Transacción Anulación"): "recarga_sonda_id_tx_anulacion",
    _norm_header("Recarga Sonda - Saldo Actualizado"): "recarga_sonda_saldo_actualizado",
}

TRANSACTIONS_HEADER_MAP: dict[str, str] = {
    _norm_header("ID"): "transaccion_id",
    _norm_header("Patente"): "patente",
    _norm_header("Fecha Entrada"): "fecha_entrada",
    _norm_header("Fecha Salida"): "fecha_salida",
    _norm_header("Fecha Cobro"): "fecha_cobro",
    _norm_header("Hora Entrada"): "hora_entrada",
    _norm_header("Hora Salida"): "hora_salida",
    _norm_header("Hora Cobro"): "hora_cobro",
    _norm_header("Tipo de Transacción"): "tipo_transaccion",
    _norm_header("Método de Ingreso"): "metodo_ingreso",
    _norm_header("Dispositivo Entrada"): "dispositivo_entrada",
    _norm_header("Dispositivo Salida"): "dispositivo_salida",
    _norm_header("Subtotal"): "subtotal",
    _norm_header("Redondeo"): "redondeo",
    _norm_header("Descuento"): "descuento",
    _norm_header("Cobrado"): "cobrado",
    _norm_header("Saldo Administrativo"): "saldo_administrativo",
    _norm_header("Metodo de pago"): "metodo_pago",
    _norm_header("Usuario Entrada"): "usuario_entrada",
    _norm_header("Usuario Salida"): "usuario_salida",
    _norm_header("Sucursal"): "sucursal",
    _norm_header("Calza"): "calza",
    _norm_header("Tipo Vehiculo"): "tipo_vehiculo",
    _norm_header("Minutos"): "minutos",
    _norm_header("Nombre Descuento"): "nombre_descuento",
    _norm_header("Cupon Descuento"): "cupon_descuento",
    _norm_header("Estado"): "estado",
    _norm_header("Comentario Entrada"): "comentario_entrada",
    _norm_header("Comentario Salida"): "comentario_salida",
    _norm_header("Folio"): "folio",
    _norm_header("Reimpresiones de Ticket de Salida"): "reimpresiones_ticket_salida",
    _norm_header("Cantidad de tickets QR impresos"): "cantidad_tickets_qr_impresos",
    _norm_header("Ticket Liberado"): "ticket_liberado",
    _norm_header("Dueño de Tarjeta"): "dueno_tarjeta",
    _norm_header("LPR Entrada"): "lpr_entrada",
    _norm_header("LPR Salida"): "lpr_salida",
    _norm_header("ID Reserva"): "id_reserva",
    _norm_header("URL"): "url",
    _norm_header("Nro Ticket"): "nro_ticket",
}

PAGOS_POLARS_SCHEMA: dict[str, pl.DataType] = {
    "sede": pl.Utf8,
    "fecha_reporte": pl.Date,
    "archivo_origen": pl.Utf8,
    "pago_id": pl.Int64,
    "transaccion_id": pl.Int64,
    "empresa": pl.Utf8,
    "sucursal": pl.Utf8,
    "calza": pl.Utf8,
    "patente": pl.Utf8,
    "operador": pl.Utf8,
    "dispositivo": pl.Utf8,
    "host": pl.Utf8,
    "minutos": pl.Int64,
    "subtotal": pl.Float64,
    "redondeo": pl.Float64,
    "descuento": pl.Float64,
    "monto": pl.Float64,
    "nombre_descuento": pl.Utf8,
    "cupon_descuento": pl.Utf8,
    "fecha_creacion": pl.Datetime("us"),
    "fecha_exito_rechazo": pl.Datetime("us"),
    "folio": pl.Utf8,
    "estado": pl.Utf8,
    "estado_sii": pl.Utf8,
    "medio_pago": pl.Utf8,
    "tipo_tarjeta": pl.Utf8,
    "nro_tarjeta": pl.Utf8,
    "servicio": pl.Utf8,
    "tipo_cobro": pl.Utf8,
    "codigo_autorizacion": pl.Utf8,
    "nro_operacion": pl.Utf8,
    "confirmacion": pl.Utf8,
    "descripcion": pl.Utf8,
    "rut_suscripcion": pl.Utf8,
    "url": pl.Utf8,
    "voucher_url": pl.Utf8,
    "recarga_sonda_id_tarjeta": pl.Utf8,
    "recarga_sonda_id_tx_carga": pl.Utf8,
    "recarga_sonda_anulada": pl.Utf8,
    "recarga_sonda_id_tx_anulacion": pl.Utf8,
    "recarga_sonda_saldo_actualizado": pl.Float64,
}

TRANSACTIONS_POLARS_SCHEMA: dict[str, pl.DataType] = {
    "sede": pl.Utf8,
    "fecha_reporte": pl.Date,
    "archivo_origen": pl.Utf8,
    "transaccion_id": pl.Int64,
    "patente": pl.Utf8,
    "fecha_entrada": pl.Date,
    "hora_entrada": pl.Utf8,
    "fecha_hora_entrada": pl.Datetime("us"),
    "fecha_salida": pl.Date,
    "hora_salida": pl.Utf8,
    "fecha_hora_salida": pl.Datetime("us"),
    "fecha_cobro": pl.Date,
    "hora_cobro": pl.Utf8,
    "fecha_hora_cobro": pl.Datetime("us"),
    "tipo_transaccion": pl.Utf8,
    "metodo_ingreso": pl.Utf8,
    "dispositivo_entrada": pl.Utf8,
    "dispositivo_salida": pl.Utf8,
    "subtotal": pl.Float64,
    "redondeo": pl.Float64,
    "descuento": pl.Float64,
    "cobrado": pl.Float64,
    "saldo_administrativo": pl.Float64,
    "metodo_pago": pl.Utf8,
    "usuario_entrada": pl.Utf8,
    "usuario_salida": pl.Utf8,
    "sucursal": pl.Utf8,
    "calza": pl.Utf8,
    "tipo_vehiculo": pl.Utf8,
    "minutos": pl.Int64,
    "nombre_descuento": pl.Utf8,
    "cupon_descuento": pl.Utf8,
    "estado": pl.Utf8,
    "comentario_entrada": pl.Utf8,
    "comentario_salida": pl.Utf8,
    "folio": pl.Utf8,
    "reimpresiones_ticket_salida": pl.Int64,
    "cantidad_tickets_qr_impresos": pl.Int64,
    "ticket_liberado": pl.Utf8,
    "dueno_tarjeta": pl.Utf8,
    "lpr_entrada": pl.Utf8,
    "lpr_salida": pl.Utf8,
    "id_reserva": pl.Utf8,
    "url": pl.Utf8,
    "nro_ticket": pl.Utf8,
}

COLUMN_MAX_LENGTHS: dict[str, int] = {
    "hora_entrada": 15,
    "hora_salida": 15,
    "hora_cobro": 15,
    "sede": 30,
    "patente": 30,
    "rut_suscripcion": 30,
    "lpr_entrada": 30,
    "lpr_salida": 30,
    "calza": 50,
    "folio": 50,
    "estado_sii": 50,
    "tipo_tarjeta": 50,
    "nro_tarjeta": 50,
    "recarga_sonda_anulada": 50,
    "ticket_liberado": 50,
    "estado": 80,
    "confirmacion": 80,
    "tipo_vehiculo": 80,
    "codigo_autorizacion": 80,
    "nro_operacion": 80,
    "recarga_sonda_id_tarjeta": 80,
    "recarga_sonda_id_tx_carga": 80,
    "recarga_sonda_id_tx_anulacion": 80,
    "id_reserva": 80,
    "nro_ticket": 80,
    "empresa": 100,
    "sucursal": 100,
    "cupon_descuento": 100,
    "medio_pago": 100,
    "metodo_pago": 100,
    "servicio": 100,
    "tipo_cobro": 100,
    "tipo_transaccion": 100,
    "metodo_ingreso": 100,
    "operador": 150,
    "dispositivo": 150,
    "host": 150,
    "nombre_descuento": 150,
    "dispositivo_entrada": 150,
    "dispositivo_salida": 150,
    "usuario_entrada": 150,
    "usuario_salida": 150,
    "dueno_tarjeta": 150,
    "archivo_origen": 255,
    "descripcion": 255,
    "url": 255,
    "comentario_entrada": 255,
    "comentario_salida": 255,
    "voucher_url": 500,
}


class RedComercioCPSBot(BaseBot):
    name = "redcomercio_cps"
    description = "Descarga, sanitiza y carga informes Excel (Pagos Exitosos y Transacciones) de ParkingApp"

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        self._batch_items: list[tuple[str, date, Path]] = []
        self._seen_export_ids: set[str] = set()

    # -------------------------------------------------------------------------
    # Resolución de parámetros y fechas
    # -------------------------------------------------------------------------
    def _resolve_reports(self) -> list[tuple[str, dict[str, str]]]:
        reporte_param = self.params.get("reporte", "todos").lower().strip()
        if reporte_param == "todos":
            return list(REPORTS_CONFIG.items())
        if reporte_param not in REPORTS_CONFIG:
            valid = ", ".join(["todos", *REPORTS_CONFIG.keys()])
            raise ValueError(f"Reporte '{reporte_param}' no válido. Opciones: {valid}")
        return [(reporte_param, REPORTS_CONFIG[reporte_param])]

    def _resolve_target_date(self) -> datetime:
        fecha_param = self.params.get("fecha", "").strip()
        if fecha_param:
            return datetime.strptime(fecha_param, "%Y-%m-%d")
        return datetime.now() - timedelta(days=1)

    # -------------------------------------------------------------------------
    # Extracción vía Playwright (admin.parkingapp.cl)
    # -------------------------------------------------------------------------
    async def _dump_debug_screenshot(self, page: Page | None, label: str) -> None:
        if not page or page.is_closed():
            return
        self.download_dir.mkdir(parents=True, exist_ok=True)
        shot_path = self.download_dir / f"debug_{label}.png"
        await page.screenshot(path=str(shot_path), full_page=True)
        self.log.warning(f"Captura de depuración guardada en: {shot_path}")

    async def _login(self, page: Page, login_url: str, user: str, password: str) -> None:
        self.log.info(f"Accediendo a {login_url}...")
        await page.goto(login_url, wait_until="domcontentloaded")

        await page.wait_for_selector("#user_session_email", state="visible")
        await page.fill("#user_session_email", user)
        await page.fill("#user_session_password", password)

        self.log.info("Enviando credenciales...")
        async with page.expect_navigation(wait_until="networkidle"):
            await page.press("#user_session_password", "Enter")

        if await page.locator("#user_session_email").is_visible():
            raise RuntimeError(f"Login fallido en {login_url}. Verifica credenciales en .env.")

        self.log.success("Sesión iniciada correctamente en ParkingApp.")

    async def _format_datepicker_value(self, locator: Locator, target_date: datetime) -> str:
        custom_fmt = self.params.get("date_fmt", "").strip()
        if custom_fmt:
            return target_date.strftime(custom_fmt)

        meta = await locator.evaluate(
            """el => ({
                fmt: el.getAttribute('data-date-format') || '',
                placeholder: el.getAttribute('placeholder') || '',
                val: el.value || ''
            })"""
        )
        hint = f"{meta['fmt']} {meta['placeholder']} {meta['val']}".lower()
        if "/" in hint:
            return target_date.strftime("%d/%m/%Y")
        return target_date.strftime("%d-%m-%Y")

    async def _set_datepicker(self, locator: Locator, date_str: str) -> None:
        await locator.wait_for(state="visible")
        await locator.evaluate(
            """(el, val) => {
                el.value = val;
                if (window.jQuery && window.jQuery(el).data('datepicker')) {
                    window.jQuery(el).datepicker('update', val);
                    window.jQuery(el).datepicker('hide');
                }
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new Event('blur', { bubbles: true }));
            }""",
            date_str,
        )

    async def _wait_for_filter_reload(self, page: Page) -> None:
        await page.wait_for_timeout(600)
        await page.wait_for_load_state("networkidle")
        spinner = page.locator(".fa-spinner:visible, .loading:visible, .blockUI:visible")
        if await spinner.count() > 0:
            await spinner.first.wait_for(state="hidden", timeout=30000)
        await page.wait_for_timeout(400)

    async def _wait_and_download_export(
        self,
        export_page: Page,
        report_key: str,
        expected_type: str,
        date_folder: str,
    ) -> Path:
        await export_page.wait_for_url("**/exportaciones**", timeout=30000)
        await export_page.wait_for_selector("table.table tbody tr", state="visible", timeout=30000)

        export_id = ""
        rows = export_page.locator("table.table tbody tr")
        row_count = min(await rows.count(), 5)

        for idx in range(row_count):
            row = rows.nth(idx)
            row_id = (await row.locator("td").nth(0).inner_text()).strip()
            row_type = (await row.locator("td").nth(3).inner_text()).strip().lower()
            action_link = row.locator("td.table-actions-cell a").first

            if row_id and row_id in self._seen_export_ids:
                continue
            if expected_type and expected_type not in row_type:
                continue

            data_url = (await action_link.get_attribute("data-url")) or ""
            href = (await action_link.get_attribute("href")) or ""
            id_match = re.search(r"/exportaciones/(\d+)", f"{data_url} {href}")
            export_id = id_match.group(1) if id_match else row_id
            break

        if not export_id:
            raise RuntimeError(
                f"[{report_key.upper()}] No se encontró una fila nueva de tipo '{expected_type}' en /exportaciones."
            )

        self._seen_export_ids.add(export_id)
        max_wait_s = int(self.params.get("wait_timeout", "900"))
        poll_interval_s = 10
        deadline = time.monotonic() + max_wait_s
        attempt = 0

        self.log.info(
            f"[{report_key.upper()}] Exportación en cola (ID={export_id}). "
            f"Esperando hasta {max_wait_s // 60} min a que pase de 'Procesando' a 'Descargar'..."
        )

        ready_link: Locator | None = None
        while time.monotonic() < deadline:
            attempt += 1

            download_candidate = export_page.locator(
                f'td.table-actions-cell a[href*="/exportaciones/{export_id}/descargar"]'
            ).first

            if await download_candidate.count() > 0:
                ready_link = download_candidate
                break

            row_cell = export_page.locator(
                f'table.table tbody tr:has(td:first-child:text-is("{export_id}")) td.table-actions-cell'
            ).first
            if await row_cell.count() > 0:
                cell_text = (await row_cell.inner_text()).strip().lower()
                if "error" in cell_text or "fall" in cell_text:
                    raise RuntimeError(
                        f"[{report_key.upper()}] ParkingApp reportó error generando ID={export_id}: '{cell_text}'."
                    )

            elapsed_s = int(max_wait_s - (deadline - time.monotonic()))
            self.log.info(
                f"[{report_key.upper()}] ID={export_id} aún procesando ({elapsed_s}s transcurridos). "
                f"Reintentando en {poll_interval_s}s..."
            )
            await asyncio.sleep(poll_interval_s)

            if attempt % 6 == 0:
                await export_page.reload(wait_until="networkidle")

        if ready_link is None:
            raise TimeoutError(
                f"[{report_key.upper()}] La exportación ID={export_id} no estuvo lista tras {max_wait_s}s."
            )

        self.log.success(f"[{report_key.upper()}] Archivo ID={export_id} listo. Iniciando descarga...")
        await ready_link.evaluate("el => el.removeAttribute('target')")
        async with export_page.expect_download(timeout=60000) as download_info:
            await ready_link.click()

        download = await download_info.value
        ext = Path(download.suggested_filename).suffix or ".xlsx"
        filename = f"{self.name}_{report_key}_{date_folder}{ext}"

        saved_path = await BrowserManager.save_download(
            download=download,
            target_dir=self.download_dir / date_folder,
            custom_name=filename,
        )

        if saved_path.stat().st_size == 0 or saved_path.read_bytes()[:2] != b"PK":
            raise RuntimeError(
                f"[{report_key.upper()}] El archivo descargado ({saved_path.name}) no es un XLSX válido."
            )

        return saved_path

    async def _export_report(
        self,
        page: Page,
        base_url: str,
        report_key: str,
        report_info: dict[str, str],
        target_date: datetime,
    ) -> Path:
        full_url = f"{base_url}{report_info['path']}"
        date_folder = target_date.strftime("%Y-%m-%d")
        self.log.info(f"=== Procesando reporte: {report_info['label']} ({full_url}) ===")

        await page.goto(full_url, wait_until="networkidle")

        if report_info["payment_status"]:
            status_select = page.locator('select[data-filter="payment_status"]').first
            await status_select.wait_for(state="attached", timeout=15000)
            await status_select.select_option(value=report_info["payment_status"], force=True)
            await status_select.evaluate("el => el.dispatchEvent(new Event('change', { bubbles: true }))")
            self.log.info(f"[{report_key.upper()}] Estado seleccionado: {report_info['payment_status']}")

        start_input = page.locator("#filter-start-date")
        end_input = page.locator("#filter-end-date")
        date_str = await self._format_datepicker_value(start_input, target_date)

        self.log.info(f"[{report_key.upper()}] Aplicando filtro de fecha: {date_str} -> {date_str}")
        await self._set_datepicker(start_input, date_str)
        await self._set_datepicker(end_input, date_str)

        filter_btn = page.locator("#filter-button")
        await filter_btn.wait_for(state="visible")
        await filter_btn.click()
        await self._wait_for_filter_reload(page)

        export_btn = page.locator("#filter-export")
        await export_btn.wait_for(state="visible")

        context = page.context
        pages_before = len(context.pages)
        await export_btn.click()
        await page.wait_for_timeout(1000)

        if len(context.pages) > pages_before:
            export_page = context.pages[-1]
            is_popup = True
        else:
            export_page = page
            is_popup = False

        try:
            saved_path = await self._wait_and_download_export(
                export_page=export_page,
                report_key=report_key,
                expected_type=report_info["expected_type"],
                date_folder=date_folder,
            )
            self._batch_items.append((report_key, target_date.date(), saved_path))
            return saved_path
        except Exception:
            await self._dump_debug_screenshot(export_page, f"{report_key}_export")
            raise
        finally:
            if is_popup and not export_page.is_closed():
                await export_page.close()

    def _discover_local_files(self, local_dir: str) -> list[Path]:
        base = Path(local_dir)
        if not base.exists():
            raise FileNotFoundError(f"La carpeta local no existe: {base}")

        allowed_reports = {k for k, _ in self._resolve_reports()}
        fecha_param = self.params.get("fecha", "").strip()
        files: list[Path] = []

        for xlsx_path in sorted(base.rglob("*.xls*")):
            if xlsx_path.name.startswith("~$"):
                continue
            fname = xlsx_path.stem.lower()
            report_key = next((k for k in ("pagos", "transacciones") if k in fname), None)
            if not report_key or report_key not in allowed_reports:
                continue

            if fecha_param:
                rep_date = datetime.strptime(fecha_param, "%Y-%m-%d").date()
            else:
                match = re.search(r"(\d{4}-\d{2}-\d{2})", xlsx_path.name) or re.search(
                    r"(\d{4}-\d{2}-\d{2})", str(xlsx_path.parent)
                )
                rep_date = (
                    datetime.strptime(match.group(1), "%Y-%m-%d").date()
                    if match
                    else (datetime.now() - timedelta(days=1)).date()
                )

            self._batch_items.append((report_key, rep_date, xlsx_path))
            files.append(xlsx_path)

        return files

    async def extract(self) -> list[Path]:
        self._batch_items.clear()
        self._seen_export_ids.clear()

        local_dir = self.params.get("local_dir", "").strip()
        if local_dir:
            self.log.info(f"Modo local activo. Buscando Excel en: {local_dir}")
            return self._discover_local_files(local_dir)

        reports = self._resolve_reports()
        target_date = self._resolve_target_date()
        report_date_iso = target_date.strftime("%Y-%m-%d")

        cfg = settings.redcomercio_cps_config
        if not cfg["user"] or not cfg["password"]:
            msg = "Faltan REDCOMERCIO_CPS_USER o REDCOMERCIO_CPS_PASS en .env."
            for report_key, _ in reports:
                self.record_error(self.name, report_key, report_date_iso, msg)
                SQLServerManager.log_execution(
                    bot_name=self.name,
                    sede=self.name,
                    reporte=report_key,
                    fecha_reporte=report_date_iso,
                    filas_insertadas=0,
                    estado="ERROR",
                    mensaje_error=msg,
                )
            raise RuntimeError(msg)

        downloaded_files: list[Path] = []
        handled_reports: set[str] = set()

        headless_param = self.params.get("headless")
        headless = None if headless_param is None else headless_param.lower() == "true"

        async with BrowserManager.get_page(headless=headless) as page:
            try:
                await self._login(page, cfg["login_url"], cfg["user"], cfg["password"])

                for report_key, report_info in reports:
                    try:
                        file_path = await self._export_report(
                            page=page,
                            base_url=cfg["base_url"],
                            report_key=report_key,
                            report_info=report_info,
                            target_date=target_date,
                        )
                        downloaded_files.append(file_path)
                        handled_reports.add(report_key)
                    except Exception as rep_exc:
                        handled_reports.add(report_key)
                        await self._dump_debug_screenshot(page, f"{report_key}_error")
                        self.log.error(f"[{report_key.upper()}] Error exportando reporte: {rep_exc}")
                        self.record_error(self.name, report_key, report_date_iso, str(rep_exc))
                        SQLServerManager.log_execution(
                            bot_name=self.name,
                            sede=self.name,
                            reporte=report_key,
                            fecha_reporte=report_date_iso,
                            filas_insertadas=0,
                            estado="ERROR",
                            mensaje_error=str(rep_exc),
                        )
            except Exception as exc:
                await self._dump_debug_screenshot(page, "general")
                for report_key, _ in reports:
                    if report_key in handled_reports:
                        continue
                    self.record_error(self.name, report_key, report_date_iso, str(exc))
                    SQLServerManager.log_execution(
                        bot_name=self.name,
                        sede=self.name,
                        reporte=report_key,
                        fecha_reporte=report_date_iso,
                        filas_insertadas=0,
                        estado="ERROR",
                        mensaje_error=str(exc),
                    )
                raise

        return downloaded_files

    # -------------------------------------------------------------------------
    # Sanitización con Polars (lectura de .xlsx con openpyxl)
    # -------------------------------------------------------------------------
    @staticmethod
    def _clean_text(raw: object) -> str | None:
        if raw is None:
            return None
        if isinstance(raw, bool):
            return "Sí" if raw else "No"
        if isinstance(raw, float):
            if math.isnan(raw):
                return None
            val_str = str(int(raw)) if raw.is_integer() else str(raw)
        else:
            val_str = str(raw)

        cleaned = " ".join(val_str.strip().split())
        return cleaned if cleaned else None

    @staticmethod
    def _parse_int(raw: object) -> int | None:
        if raw is None:
            return None
        if isinstance(raw, bool):
            return int(raw)
        if isinstance(raw, (int, float)):
            if isinstance(raw, float) and math.isnan(raw):
                return None
            return int(round(raw))

        val = str(raw).strip().replace(",", "").replace(".", "")
        return int(val) if val else None

    @staticmethod
    def _parse_float(raw: object, default_zero: bool = True) -> float | None:
        if raw is None:
            return 0.0 if default_zero else None
        if isinstance(raw, (int, float)):
            if isinstance(raw, float) and math.isnan(raw):
                return 0.0 if default_zero else None
            return round(float(raw), 2)

        val = str(raw).strip().replace("$", "").replace(" ", "")
        if not val:
            return 0.0 if default_zero else None

        if "," in val and "." in val:
            if val.rfind(",") > val.rfind("."):
                cleaned = val.replace(".", "").replace(",", ".")
            else:
                cleaned = val.replace(",", "")
        elif "," in val:
            cleaned = val.replace(",", ".")
        elif "." in val:
            cleaned = val.replace(".", "") if val.count(".") > 1 else val
        else:
            cleaned = val

        return round(float(cleaned), 2)

    @staticmethod
    def _parse_datetime(raw: object) -> datetime | None:
        if raw is None:
            return None
        if isinstance(raw, datetime):
            return raw.replace(microsecond=0)
        if isinstance(raw, date):
            return datetime(raw.year, raw.month, raw.day)

        val = str(raw).strip()
        if not val:
            return None

        for fmt in (
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y %H:%M:%S",
            "%d-%m-%Y %H:%M",
            "%d-%m-%Y %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d/%m/%Y",
            "%d-%m-%Y",
        ):
            try:
                return datetime.strptime(val, fmt)
            except ValueError:
                continue
        raise ValueError(f"Formato de fecha/hora inesperado en ParkingApp: '{val}'")

    @staticmethod
    def _parse_date(raw: object) -> date | None:
        if raw is None:
            return None
        if isinstance(raw, datetime):
            return raw.date()
        if isinstance(raw, date):
            return raw

        val = str(raw).strip()
        if not val:
            return None

        date_part = val.split()[0]
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(date_part, fmt).date()
            except ValueError:
                continue
        raise ValueError(f"Formato de fecha inesperado en ParkingApp: '{val}'")

    @staticmethod
    def _parse_time_str(raw: object) -> str | None:
        if raw is None:
            return None
        if isinstance(raw, datetime):
            return raw.strftime("%H:%M:%S")
        if isinstance(raw, dt_time):
            return raw.strftime("%H:%M:%S")

        val = str(raw).strip()
        return val if val else None

    @staticmethod
    def _combine_date_time(d_val: date | None, t_str: str | None) -> datetime | None:
        if d_val is None:
            return None
        if not t_str:
            return datetime(d_val.year, d_val.month, d_val.day)

        parts = t_str.split(":")
        try:
            hour = int(parts[0]) if len(parts) >= 1 else 0
            minute = int(parts[1]) if len(parts) >= 2 else 0
            second = int(parts[2]) if len(parts) >= 3 else 0
            return datetime(d_val.year, d_val.month, d_val.day, hour, minute, second)
        except ValueError:
            return datetime(d_val.year, d_val.month, d_val.day)

    def _build_polars_df(self, report_key: str, rep_date: date, xlsx_path: Path) -> pl.DataFrame:
        schema = PAGOS_POLARS_SCHEMA if report_key == "pagos" else TRANSACTIONS_POLARS_SCHEMA
        header_map = PAGOS_HEADER_MAP if report_key == "pagos" else TRANSACTIONS_HEADER_MAP

        wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
        try:
            ws = wb.active
            rows_iter = ws.iter_rows(values_only=True)
            header_row = next(rows_iter, None)

            if not header_row:
                self.log.warning(f"[{report_key.upper()}] Excel vacío: {xlsx_path.name}")
                return pl.DataFrame(schema=schema)

            raw_headers = [str(h).strip() if h is not None else "" for h in header_row]
            canonical_headers = [header_map.get(_norm_header(h), "") for h in raw_headers]

            unknown_headers = [h for h, c in zip(raw_headers, canonical_headers) if h and not c]
            if unknown_headers:
                self.log.warning(
                    f"[{report_key.upper()}] Columnas nuevas ignoradas en {xlsx_path.name}: {unknown_headers}"
                )

            int_fields = {
                "pago_id",
                "transaccion_id",
                "minutos",
                "reimpresiones_ticket_salida",
                "cantidad_tickets_qr_impresos",
            }
            zero_float_fields = {
                "subtotal",
                "redondeo",
                "descuento",
                "monto",
                "cobrado",
                "saldo_administrativo",
            }
            nullable_float_fields = {"recarga_sonda_saldo_actualizado"}
            datetime_fields = {"fecha_creacion", "fecha_exito_rechazo"}
            date_fields = {"fecha_entrada", "fecha_salida", "fecha_cobro"}
            time_fields = {"hora_entrada", "hora_salida", "hora_cobro"}

            sanitized_records: list[dict[str, object]] = []
            for row_values in rows_iter:
                if not any(cell is not None and str(cell).strip() != "" for cell in row_values):
                    continue

                raw_dict: dict[str, object] = {}
                for col_key, cell_val in zip(canonical_headers, row_values):
                    if col_key:
                        raw_dict[col_key] = cell_val

                clean_row: dict[str, object] = {}
                for col in schema:
                    if col == "sede":
                        clean_row[col] = self.name
                    elif col == "fecha_reporte":
                        clean_row[col] = rep_date
                    elif col == "archivo_origen":
                        clean_row[col] = xlsx_path.name
                    elif col in ("fecha_hora_entrada", "fecha_hora_salida", "fecha_hora_cobro"):
                        continue  # Se calculan justo debajo al tener fecha y hora parseadas
                    elif col in int_fields:
                        clean_row[col] = self._parse_int(raw_dict.get(col))
                    elif col in zero_float_fields:
                        clean_row[col] = self._parse_float(raw_dict.get(col), default_zero=True)
                    elif col in nullable_float_fields:
                        clean_row[col] = self._parse_float(raw_dict.get(col), default_zero=False)
                    elif col in datetime_fields:
                        clean_row[col] = self._parse_datetime(raw_dict.get(col))
                    elif col in date_fields:
                        clean_row[col] = self._parse_date(raw_dict.get(col))
                    elif col in time_fields:
                        clean_row[col] = self._parse_time_str(raw_dict.get(col))
                    else:
                        clean_row[col] = self._clean_text(raw_dict.get(col))

                if report_key == "transacciones":
                    clean_row["fecha_hora_entrada"] = self._combine_date_time(
                        clean_row.get("fecha_entrada"), clean_row.get("hora_entrada")  # type: ignore[arg-type]
                    )
                    clean_row["fecha_hora_salida"] = self._combine_date_time(
                        clean_row.get("fecha_salida"), clean_row.get("hora_salida")  # type: ignore[arg-type]
                    )
                    clean_row["fecha_hora_cobro"] = self._combine_date_time(
                        clean_row.get("fecha_cobro"), clean_row.get("hora_cobro")  # type: ignore[arg-type]
                    )

                sanitized_records.append(clean_row)
        finally:
            wb.close()

        if not sanitized_records:
            return pl.DataFrame(schema=schema)

        df = pl.DataFrame(sanitized_records, schema=schema)

        truncate_exprs = [
            pl.col(col).str.slice(0, max_len).alias(col)
            for col, max_len in COLUMN_MAX_LENGTHS.items()
            if col in df.columns
        ]
        if truncate_exprs:
            df = df.with_columns(truncate_exprs)

        self.log.info(
            f"[{report_key.upper()}] DataFrame sanitizado: {df.height} filas (archivo={xlsx_path.name})"
        )
        return df

    def transform(self, files: list[Path]) -> list[tuple[str, str, str, pl.DataFrame]]:
        batches: list[tuple[str, str, str, pl.DataFrame]] = []

        if not self._batch_items and files:
            for f in files:
                fname = f.stem.lower()
                report_key = "pagos" if "pagos" in fname else "transacciones"
                match = re.search(r"(\d{4}-\d{2}-\d{2})", f.name) or re.search(
                    r"(\d{4}-\d{2}-\d{2})", str(f.parent)
                )
                rep_date = (
                    datetime.strptime(match.group(1), "%Y-%m-%d").date()
                    if match
                    else (datetime.now() - timedelta(days=1)).date()
                )
                self._batch_items.append((report_key, rep_date, f))

        for report_key, rep_date, xlsx_path in self._batch_items:
            df = self._build_polars_df(report_key, rep_date, xlsx_path)
            batches.append((self.name, report_key, rep_date.isoformat(), df))

        return batches

    # -------------------------------------------------------------------------
    # Carga vía SQLServerManager (con reintentos VPN y lotes de 15 filas)
    # -------------------------------------------------------------------------
    def load(self, batches: list[tuple[str, str, str, pl.DataFrame]]) -> int:
        if not batches:
            return 0

        SQLServerManager.check_connection()
        total_inserted = 0

        for sede_key, report_key, report_date_iso, report_df in batches:
            if report_df.is_empty():
                SQLServerManager.log_execution(
                    bot_name=self.name,
                    sede=sede_key,
                    reporte=report_key,
                    fecha_reporte=report_date_iso,
                    filas_insertadas=0,
                    estado="SIN_DATOS",
                )
                continue

            table_name = REPORTS_CONFIG[report_key]["table"]
            inserted = SQLServerManager.replace_by_sede_and_dates(
                df=report_df,
                table_name=table_name,
                sede=sede_key,
                date_column="fecha_reporte",
                schema="dbo",
            )
            total_inserted += inserted
            SQLServerManager.log_execution(
                bot_name=self.name,
                sede=sede_key,
                reporte=report_key,
                fecha_reporte=report_date_iso,
                filas_insertadas=inserted,
                estado="OK",
            )

        return total_inserted