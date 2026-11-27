import csv
from datetime import date, datetime, timedelta
from pathlib import Path
import re
import polars as pl
from playwright.async_api import Dialog, FrameLocator, Locator, Page
from config.settings import settings
from core.base_bot import BaseBot
from core.browser import BrowserManager
from core.database import SQLServerManager

class NoDataAvailableError(Exception):
    """El portal confirmó que no existen registros para la fecha consultada."""


REPORTS_CONFIG: dict[str, dict[str, str]] = {
    "transacciones": {
        "label": "Informe de Transacciones",
        "category_toggle_id": "#ctl00_iParcMenu_Report_IParcMenu1_ImageMenus_Ctrlt1",
        "nodes_container_id": "#ctl00_iParcMenu_Report_IParcMenu1_ImageMenus_Ctrln1Nodes",
        "href": "TransactionReport.aspx",
    },
    "tracking": {
        "label": "Informe de Seguimiento (Tracking)",
        "category_toggle_id": "#ctl00_iParcMenu_Report_IParcMenu1_ImageMenus_Ctrlt30",
        "nodes_container_id": "#ctl00_iParcMenu_Report_IParcMenu1_ImageMenus_Ctrln30Nodes",
        "href": "TrackingReport.aspx",
    },
}

PARKING_LOT_TO_SEDE: dict[str, str] = {
    "puente la dehesa": "pld",
    "mall paseo shopping quillota": "quillota",
    "homecenter las condes": "homecenter",
    "strip center pte alto": "plazuela",
    "cl. indisa los conquistadores": "conquistadores",
}

TRACKING_HEADER_MAP: dict[str, str] = {
    "Parking Lot": "parking_lot",
    "Estacionamiento": "parking_lot",
    "Card Type": "card_type",
    "Tipo de tarjeta": "card_type",
    "Card Number": "card_number",
    "Card No.": "card_number",
    "Tarjeta Nº": "card_number",
    "Entry Equipment": "entry_equipment",
    "Equipo de entrada": "entry_equipment",
    "Entry Date": "entry_date",
    "Fecha de entrada": "entry_date",
    "Payment Equipment": "payment_equipment",
    "Equipo de pago": "payment_equipment",
    "Payment Date": "payment_date",
    "Fecha de pago": "payment_date",
    "Exit Equipment": "exit_equipment",
    "Equipo de salida": "exit_equipment",
    "Exit Date": "exit_date",
    "Fecha de salida": "exit_date",
    "Fee Rate": "fee_rate",
    "Tipo de tarifa": "fee_rate",
    "Parking Fee": "parking_fee",
    "Fee": "parking_fee",
    "Tarifa del estacionamiento": "parking_fee",
    "Tarifa": "parking_fee",
    "Cash Sales": "cash_sales",
    "Cash": "cash_sales",
    "Ventas en efectivo": "cash_sales",
    "Efectivo": "cash_sales",
    "Credit Sales": "credit_sales",
    "Credit": "credit_sales",
    "Ventas a crédito": "credit_sales",
    "Crédito": "credit_sales",
    "Disc Total": "disc_total",
    "Discount": "disc_total",
    "Total descuentos": "disc_total",
    "Descuento": "disc_total",
    "Misc Sales": "misc_sales",
    "Miscellaneous": "misc_sales",
    "Ventas misceláneas": "misc_sales",
    "Misceláneas": "misc_sales",
    "Cashier": "cashier",
    "Cajero": "cashier",
    "License Plate": "license_plate",
    "Plate": "license_plate",
    "Patente": "license_plate",
}

TRANSACTIONS_HEADER_MAP: dict[str, str] = {
    "Parking Lot": "parking_lot",
    "Estacionamiento": "parking_lot",
    "Area ID": "area_id",
    "ID de área": "area_id",
    "Area Name": "area_name",
    "Nombre de área": "area_name",
    "Equipment": "equipment",
    "Equipo": "equipment",
    "Cashier": "cashier",
    "Cajero": "cashier",
    "T-Total Number": "t_total_number",
    "Número T-Total": "t_total_number",
    "Paid Equipment Number": "paid_equipment_number",
    "Número de equipo de pagados": "paid_equipment_number",
    "Entry Equipment Number": "entry_equipment_number",
    "Número de equipo de entrada": "entry_equipment_number",
    "Exit Equipment Number": "exit_equipment_number",
    "Número de equipo de salida": "exit_equipment_number",
    "Payment Date": "payment_date",
    "Fecha de pago": "payment_date",
    "Entry Date": "entry_date",
    "Fecha de entrada": "entry_date",
    "Exit Date": "exit_date",
    "Fecha de salida": "exit_date",
    "Payment Type": "payment_type",
    "Tipo de pago": "payment_type",
    "Card Type": "card_type",
    "Tipo de tarjeta": "card_type",
    "Fee Rate / Pass Card Type": "fee_rate_pass_card_type",
    "Tipo de tarifa / Tipo de abonado": "fee_rate_pass_card_type",
    "Card Number": "card_number",
    "Tarjeta Nº": "card_number",
    "Parking Fee": "parking_fee",
    "Tarifa del estacionamiento": "parking_fee",
    "Payment": "payment",
    "Pago": "payment",
    "Credit": "credit",
    "Crédito": "credit",
    "Fiscal Receipt No.1": "fiscal_receipt_no_1",
    "Núm. Boleta Fiscal 1": "fiscal_receipt_no_1",
    "Fiscal Amount1": "fiscal_amount_1",
    "Monto Fiscal 1": "fiscal_amount_1",
    "Fiscal Receipt No.2": "fiscal_receipt_no_2",
    "Núm. Boleta Fiscal 2": "fiscal_receipt_no_2",
    "Fiscal Amount2": "fiscal_amount_2",
    "Monto Fiscal 2": "fiscal_amount_2",
    "Fiscal Receipt No.3": "fiscal_receipt_no_3",
    "Núm. Boleta Fiscal 3": "fiscal_receipt_no_3",
    "Fiscal Amount3": "fiscal_amount_3",
    "Monto Fiscal 3": "fiscal_amount_3",
}

for _idx in range(1, 10):
    TRANSACTIONS_HEADER_MAP[f"Card Type{_idx}"] = f"card_type_{_idx}"
    TRANSACTIONS_HEADER_MAP[f"Tipo de tarjeta {_idx}"] = f"card_type_{_idx}"
    TRANSACTIONS_HEADER_MAP[f"Discount Num{_idx}"] = f"discount_num_{_idx}"
    TRANSACTIONS_HEADER_MAP[f"Descuento número {_idx}"] = f"discount_num_{_idx}"
    TRANSACTIONS_HEADER_MAP[f"Número de descuento {_idx}"] = f"discount_num_{_idx}"
    TRANSACTIONS_HEADER_MAP[f"Discount{_idx}"] = f"discount_{_idx}"
    TRANSACTIONS_HEADER_MAP[f"Descuento {_idx}"] = f"discount_{_idx}"

TRACKING_POLARS_SCHEMA: dict[str, pl.DataType] = {
    "sede": pl.Utf8,
    "fecha_reporte": pl.Date,
    "archivo_origen": pl.Utf8,
    "parking_lot": pl.Utf8,
    "card_type": pl.Utf8,
    "card_number": pl.Utf8,
    "entry_equipment": pl.Utf8,
    "entry_date": pl.Datetime("us"),
    "payment_equipment": pl.Utf8,
    "payment_date": pl.Datetime("us"),
    "exit_equipment": pl.Utf8,
    "exit_date": pl.Datetime("us"),
    "fee_rate": pl.Utf8,
    "parking_fee": pl.Float64,
    "cash_sales": pl.Float64,
    "credit_sales": pl.Float64,
    "disc_total": pl.Float64,
    "misc_sales": pl.Float64,
    "cashier": pl.Utf8,
    "license_plate": pl.Utf8,
}

TRANSACTIONS_POLARS_SCHEMA: dict[str, pl.DataType] = {
    "sede": pl.Utf8,
    "fecha_reporte": pl.Date,
    "archivo_origen": pl.Utf8,
    "parking_lot": pl.Utf8,
    "area_id": pl.Int64,
    "area_name": pl.Utf8,
    "equipment": pl.Utf8,
    "cashier": pl.Utf8,
    "t_total_number": pl.Int64,
    "paid_equipment_number": pl.Int64,
    "entry_equipment_number": pl.Int64,
    "exit_equipment_number": pl.Int64,
    "payment_date": pl.Datetime("us"),
    "entry_date": pl.Datetime("us"),
    "exit_date": pl.Datetime("us"),
    "payment_type": pl.Utf8,
    "card_type": pl.Utf8,
    "fee_rate_pass_card_type": pl.Utf8,
    "card_number": pl.Utf8,
    "parking_fee": pl.Float64,
    "payment": pl.Float64,
    "credit": pl.Float64,
    **{
        col: dtype
        for i in range(1, 10)
        for col, dtype in (
            (f"card_type_{i}", pl.Utf8),
            (f"discount_num_{i}", pl.Utf8),
            (f"discount_{i}", pl.Float64),
        )
    },
    "fiscal_receipt_no_1": pl.Utf8,
    "fiscal_amount_1": pl.Float64,
    "fiscal_receipt_no_2": pl.Utf8,
    "fiscal_amount_2": pl.Float64,
    "fiscal_receipt_no_3": pl.Utf8,
    "fiscal_amount_3": pl.Float64,
}

AMANO_JP_MAX_LENGTHS: dict[str, int] = {
    "sede": 30,
    "license_plate": 20,
    "card_type": 50,
    "fee_rate_pass_card_type": 50,
    "card_number": 50,
    "fee_rate": 50,
    "fiscal_receipt_no_1": 50,
    "fiscal_receipt_no_2": 50,
    "fiscal_receipt_no_3": 50,
    **{f"card_type_{i}": 50 for i in range(1, 10)},
    **{f"discount_num_{i}": 50 for i in range(1, 10)},
    "payment_type": 80,
    "parking_lot": 100,
    "area_name": 100,
    "equipment": 100,
    "cashier": 100,
    "entry_equipment": 100,
    "payment_equipment": 100,
    "exit_equipment": 100,
    "archivo_origen": 255,
}


class AmanoJaponBot(BaseBot):
    name = "amano_japon"
    description = "Descarga, sanitiza y carga informes (Transacciones y Tracking) de Amano ExACT a SQL Server"

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        self._batch_items: list[tuple[str, str, date, Path]] = []

    # -------------------------------------------------------------------------
    # Resolución de parámetros
    # -------------------------------------------------------------------------
    def _resolve_sites(self) -> list[tuple[str, dict[str, str]]]:
        sede_param = self.params.get("sede", "todas").lower().strip()
        all_sites = settings.amano_japon_sites

        if sede_param == "todas":
            return list(all_sites.items())
        if sede_param not in all_sites:
            valid = ", ".join(["todas", *all_sites.keys()])
            raise ValueError(f"Sede '{sede_param}' no válida. Opciones: {valid}")
        return [(sede_param, all_sites[sede_param])]

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

    @staticmethod
    def _format_date_for_exact(target_date: datetime, is_english: bool, existing_sample: str) -> str:
        parts = existing_sample.strip().split("/")
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            first, second = int(parts[0]), int(parts[1])
            if first > 12:
                is_english = False
            elif second > 12:
                is_english = True

        return target_date.strftime("%m/%d/%Y" if is_english else "%d/%m/%Y")

    # -------------------------------------------------------------------------
    # Extracción vía Playwright (ExACT)
    # -------------------------------------------------------------------------
    async def _login(self, page: Page, login_url: str, user: str, password: str) -> None:
        self.log.info(f"Accediendo a {login_url}...")
        await page.goto(login_url, wait_until="domcontentloaded")

        await page.wait_for_selector("#userIDText", state="visible")
        await page.fill("#userIDText", user)
        await page.fill("#Password", password)

        self.log.info("Enviando credenciales...")
        async with page.expect_navigation(wait_until="networkidle"):
            await page.press("#Password", "Enter")

        if await page.locator("#userIDText").is_visible():
            raise RuntimeError(f"Login fallido en {login_url}. Verifica usuario y contraseña en .env.")

        self.log.success("Sesión iniciada correctamente.")

    async def _open_reports_popup(self, page: Page) -> tuple[Page, bool]:
        buttons = page.locator("#ItemList .Button")
        await buttons.nth(1).wait_for(state="visible")

        btn_text = (await buttons.nth(1).locator(".ButtonText").inner_text()).strip().upper()
        is_english = "REPORT" in btn_text
        self.log.info(f"Abriendo módulo '{btn_text}' (idioma inicial: {'EN' if is_english else 'ES'})...")

        async with page.expect_popup() as popup_info:
            await buttons.nth(1).click()

        popup = await popup_info.value
        await popup.wait_for_load_state("domcontentloaded")
        return popup, is_english

    async def _detect_menu_language(self, frame: FrameLocator, fallback_english: bool) -> bool:
        menu_root = frame.locator("div#ctl00_iParcMenu_Report_IParcMenu1_ImageMenus_Ctrln0Nodes")
        await menu_root.wait_for(state="attached")
        menu_text = (await menu_root.inner_text()).lower()

        if "sales report" in menu_text or "history report" in menu_text:
            detected = True
        elif "informe de ventas" in menu_text or "informe histórico" in menu_text:
            detected = False
        else:
            detected = fallback_english

        self.log.info(f"Idioma detectado en el menú del iframe: {'EN' if detected else 'ES'}")
        return detected

    async def _fill_exact_date(self, locator: Locator, date_str: str) -> None:
        await locator.evaluate(
            """(el, val) => {
                el.focus();
                el.value = val;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                if (typeof TextFocusOFF === 'function') {
                    TextFocusOFF({ type: 'blur', target: el }, el.id);
                }
                el.dispatchEvent(new Event('blur', { bubbles: true }));
            }""",
            date_str,
        )

        current_val = (await locator.input_value()).strip()
        if current_val != date_str:
            digits_only = date_str.replace("/", "")
            await locator.click()
            await locator.evaluate("el => el.setSelectionRange(0, 0)")
            await locator.type(digits_only, delay=30)
            await locator.evaluate(
                """(el) => {
                    if (typeof TextFocusOFF === 'function') {
                        TextFocusOFF({ type: 'blur', target: el }, el.id);
                    }
                    el.dispatchEvent(new Event('blur', { bubbles: true }));
                }"""
            )

    async def _dump_debug_artifacts(self, popup: Page | None, sede_key: str) -> None:
        self.download_dir.mkdir(parents=True, exist_ok=True)
        if not popup or popup.is_closed():
            return

        debug_shot = self.download_dir / f"debug_{sede_key}.png"
        await popup.screenshot(path=str(debug_shot), full_page=True)
        self.log.warning(f"[{sede_key.upper()}] Captura de depuración guardada en: {debug_shot}")

    async def _download_report(
        self,
        popup: Page,
        frame: FrameLocator,
        sede_key: str,
        report_key: str,
        report_info: dict[str, str],
        target_date: datetime,
        is_english: bool,
        dialogs: list[str],
    ) -> Path:
        self.log.info(f"[{sede_key.upper()}] Abriendo {report_info['label']}...")

        old_start = frame.locator("#ctl00_contents_panel_itbvStartDate_ImgText")
        if await old_start.count() > 0:
            await old_start.evaluate("el => { el.dataset.staleReport = '1'; }")

        category_link = frame.locator(report_info["category_toggle_id"])
        await category_link.wait_for(state="attached")
        await category_link.evaluate("el => el.click()")

        item_link = frame.locator(f'a[href="{report_info["href"]}"]')
        await item_link.wait_for(state="attached")
        await item_link.evaluate("el => el.click()")

        await frame.locator('#ctl00_contents_panel_itbvStartDate_ImgText[data-stale-report="1"]').wait_for(
            state="detached", timeout=15000
        )
        iframe_handle = await popup.locator("#iParcMainFrame").element_handle()
        if iframe_handle:
            content_frame = await iframe_handle.content_frame()
            if content_frame:
                await content_frame.wait_for_url(f"**/{report_info['href']}*", timeout=15000)
                await content_frame.wait_for_load_state("networkidle")

        start_input = frame.locator("#ctl00_contents_panel_itbvStartDate_ImgText")
        end_input = frame.locator("#ctl00_contents_panel_itbvEndDate_ImgText")
        await start_input.wait_for(state="visible", timeout=15000)
        await popup.wait_for_timeout(300)

        existing_sample = await start_input.input_value()
        date_str = self._format_date_for_exact(target_date, is_english, existing_sample)
        lang_tag = "EN (MM/DD/YYYY)" if is_english else "ES (DD/MM/YYYY)"
        self.log.info(
            f"[{sede_key.upper()}] Muestra actual='{existing_sample}' -> Aplicando fecha {date_str} [{lang_tag}]..."
        )

        await self._fill_exact_date(start_input, date_str)
        await self._fill_exact_date(end_input, date_str)

        export_btn = frame.locator("input#ctl00_btnRight")
        await export_btn.wait_for(state="visible")
        dialogs.clear()

        iframe_reloaded = False
        if content_frame:
            def _on_frame_load(_frame) -> None:
                nonlocal iframe_reloaded
                iframe_reloaded = True

            content_frame.on("load", _on_frame_load)

        try:
            async with popup.expect_download(timeout=35000) as download_info:
                await export_btn.click()
        except Exception as exc:
            no_data_tokens = (
                "no data",
                "no hay datos",
                "sin datos",
                "no record",
                "no se encontr",
                "0 record",
                "ningún registro",
                "there is no data",
            )
            if dialogs:
                dialog_msg = " | ".join(dialogs)
                if any(tok in dialog_msg.lower() for tok in no_data_tokens):
                    raise NoDataAvailableError(
                        f"Portal ExACT sin registros para {date_str}: '{dialog_msg}'"
                    ) from exc
                raise RuntimeError(f"ExACT mostró alerta en {report_key}: {dialog_msg}") from exc

            page_text = ""
            if content_frame:
                try:
                    page_text = (await content_frame.locator("body").inner_text(timeout=3000)).strip()
                except Exception:
                    pass

            matched_line = next(
                (
                    line.strip()
                    for line in page_text.splitlines()
                    if any(tok in line.lower() for tok in no_data_tokens)
                ),
                "",
            )
            if matched_line:
                raise NoDataAvailableError(
                    f"Portal ExACT sin registros para {date_str}: '{matched_line}'"
                ) from exc

            if iframe_reloaded:
                raise NoDataAvailableError(
                    f"Portal ExACT respondió la consulta para {date_str} sin generar archivo (0 registros)."
                ) from exc

            raise

        download = await download_info.value
        date_folder = target_date.strftime("%Y-%m-%d")
        filename = f"{sede_key}_{report_key}_{date_folder}.csv"

        saved_path = await BrowserManager.save_download(
            download=download,
            target_dir=self.download_dir / date_folder / sede_key,
            custom_name=filename,
        )
        return saved_path

    def _discover_local_files(self, local_dir: str) -> list[Path]:
        base = Path(local_dir)
        if not base.exists():
            raise FileNotFoundError(f"La carpeta local no existe: {base}")

        sede_filter = self.params.get("sede", "todas").lower().strip()
        report_filter = self.params.get("reporte", "todos").lower().strip()

        files: list[Path] = []
        for csv_path in sorted(base.rglob("*.csv")):
            sede_key, report_key, rep_date = self._infer_file_metadata(csv_path)
            if sede_filter != "todas" and sede_key != sede_filter:
                continue
            if report_filter != "todos" and report_key != report_filter:
                continue
            self._batch_items.append((sede_key, report_key, rep_date, csv_path))
            files.append(csv_path)

        return files

    async def extract(self) -> list[Path]:
        self._batch_items.clear()

        local_dir = self.params.get("local_dir", "").strip()
        if local_dir:
            self.log.info(f"Modo local activo. Buscando CSV en: {local_dir}")
            return self._discover_local_files(local_dir)

        sites = self._resolve_sites()
        reports = self._resolve_reports()
        target_date = self._resolve_target_date()
        report_date_obj = target_date.date()
        report_date_iso = report_date_obj.isoformat()
        downloaded_files: list[Path] = []

        headless_param = self.params.get("headless")
        headless = None if headless_param is None else headless_param.lower() == "true"

        for sede_key, site in sites:
            self.log.info(f"=== Procesando sede: {site['nombre']} ({site['login_url']}) ===")
            if not site["user"] or not site["password"]:
                self.log.error(f"Credenciales faltantes en .env para '{sede_key}'. Saltando sede.")
                continue

            popup: Page | None = None
            dialogs: list[str] = []

            try:
                async with BrowserManager.get_page(headless=headless) as page:
                    await self._login(page, site["login_url"], site["user"], site["password"])
                    popup, is_english = await self._open_reports_popup(page)

                    async def _on_dialog(dialog: Dialog) -> None:
                        dialogs.append(dialog.message)
                        self.log.warning(f"[{sede_key.upper()}] Alerta ExACT: {dialog.message}")
                        await dialog.accept()

                    popup.on("dialog", _on_dialog)

                    try:
                        frame = popup.frame_locator("#iParcMainFrame")
                        is_english = await self._detect_menu_language(frame, is_english)

                        for report_key, report_info in reports:
                            try:
                                file_path = await self._download_report(
                                    popup=popup,
                                    frame=frame,
                                    sede_key=sede_key,
                                    report_key=report_key,
                                    report_info=report_info,
                                    target_date=target_date,
                                    is_english=is_english,
                                    dialogs=dialogs,
                                )
                                self._batch_items.append((sede_key, report_key, report_date_obj, file_path))
                                downloaded_files.append(file_path)
                                self.log.success(f"[{sede_key.upper()}] CSV guardado en: {file_path}")
                            except NoDataAvailableError as nd_exc:
                                self.log.warning(f"[{sede_key.upper()} - {report_key.upper()}] {nd_exc}")
                                SQLServerManager.log_execution(
                                    bot_name=self.name,
                                    sede=sede_key,
                                    reporte=report_key,
                                    fecha_reporte=report_date_iso,
                                    filas_insertadas=0,
                                    estado="SIN_DATOS",
                                    mensaje_error=str(nd_exc),
                                )
                            except Exception as rep_exc:
                                await self._dump_debug_artifacts(popup, f"{sede_key}_{report_key}")
                                self.log.error(
                                    f"[{sede_key.upper()} - {report_key.upper()}] Error en reporte: {rep_exc}"
                                )
                                SQLServerManager.log_execution(
                                    bot_name=self.name,
                                    sede=sede_key,
                                    reporte=report_key,
                                    fecha_reporte=report_date_iso,
                                    filas_insertadas=0,
                                    estado="ERROR",
                                    mensaje_error=str(rep_exc),
                                )
                    except Exception:
                        await self._dump_debug_artifacts(popup, sede_key)
                        raise
                    finally:
                        if popup and not popup.is_closed():
                            await popup.close()
            except Exception as exc:
                self.log.error(f"[{sede_key.upper()}] Error procesando sede: {exc}")
                SQLServerManager.log_execution(
                    bot_name=self.name,
                    sede=sede_key,
                    reporte="todos",
                    fecha_reporte=report_date_iso,
                    filas_insertadas=0,
                    estado="ERROR",
                    mensaje_error=str(exc),
                )

        return downloaded_files

    # -------------------------------------------------------------------------
    # Sanitización con Polars (EN/ES, 43/44 cols, fechas sin ambigüedad)
    # -------------------------------------------------------------------------
    def _infer_file_metadata(self, csv_path: Path) -> tuple[str, str, date]:
        name_lower = csv_path.name.lower()
        parent_lower = csv_path.parent.name.lower()

        if "track" in name_lower:
            report_key = "tracking"
        elif "transac" in name_lower or "tranaction" in name_lower:
            report_key = "transacciones"
        else:
            first_line = csv_path.read_text(encoding="utf-8-sig", errors="replace").splitlines()[0]
            report_key = (
                "tracking"
                if ("Exit Equipment" in first_line or "Equipo de salida" in first_line)
                else "transacciones"
            )

        sede_key = ""
        known_sedes = tuple(settings.amano_japon_sites.keys())
        if parent_lower in known_sedes:
            sede_key = parent_lower
        else:
            for candidate in known_sedes:
                if candidate in name_lower:
                    sede_key = candidate
                    break
            if not sede_key and "conquistadores" in name_lower:
                sede_key = "conquistadores"

        if not sede_key:
            with csv_path.open("r", encoding="utf-8-sig", errors="replace") as fh:
                reader = csv.reader(fh)
                next(reader, None)
                first_row = next(reader, None)
                if first_row:
                    sede_key = PARKING_LOT_TO_SEDE.get(first_row[0].strip().lower(), "desconocida")

        fecha_param = self.params.get("fecha", "").strip()
        if fecha_param:
            rep_date = datetime.strptime(fecha_param, "%Y-%m-%d").date()
        else:
            match = re.search(r"(\d{4}-\d{2}-\d{2})", csv_path.name) or re.search(
                r"(\d{4}-\d{2}-\d{2})", str(csv_path.parent)
            )
            if match:
                rep_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
            else:
                rep_date = (datetime.now() - timedelta(days=1)).date()

        return sede_key, report_key, rep_date

    @staticmethod
    def _detect_csv_language(headers: list[str], rows: list[list[str]], date_col_indices: list[int]) -> str:
        header_lang = "ES" if headers and headers[0].strip().lower() == "estacionamiento" else "EN"

        for row in rows[:500]:
            for idx in date_col_indices:
                if idx >= len(row):
                    continue
                raw = row[idx].strip()
                if not raw:
                    continue
                date_part = raw.split(" ")[0]
                parts = date_part.split("/")
                if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
                    p1, p2 = int(parts[0]), int(parts[1])
                    if p1 > 12:
                        return "ES"
                    if p2 > 12:
                        return "EN"

        return header_lang

    @staticmethod
    def _parse_exact_datetime(raw: str | None, csv_lang: str) -> datetime | None:
        if not raw:
            return None
        val = raw.strip()
        if not val:
            return None

        formats = (
            ("%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y")
            if csv_lang == "EN"
            else ("%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y")
        )
        for fmt in formats:
            try:
                return datetime.strptime(val, fmt)
            except ValueError:
                continue
        raise ValueError(f"Formato de fecha inesperado '{val}' (idioma={csv_lang})")

    @staticmethod
    def _parse_exact_float(raw: str | None, csv_lang: str, default_zero: bool = True) -> float | None:
        if raw is None:
            return 0.0 if default_zero else None
        val = raw.strip()
        if not val:
            return 0.0 if default_zero else None

        if "," in val and "." in val:
            if val.rfind(",") > val.rfind("."):
                cleaned = val.replace(".", "").replace(",", ".")
            else:
                cleaned = val.replace(",", "")
        elif "," in val:
            cleaned = val.replace(",", "") if csv_lang == "EN" else val.replace(",", ".")
        elif "." in val:
            if val.count(".") > 1 or csv_lang == "ES":
                cleaned = val.replace(".", "")
            else:
                cleaned = val
        else:
            cleaned = val

        return round(float(cleaned), 2)

    @staticmethod
    def _parse_exact_int(raw: str | None) -> int | None:
        if raw is None:
            return None
        val = raw.strip().replace(",", "").replace(".", "")
        return int(val) if val else None

    @staticmethod
    def _clean_text(raw: str | None) -> str | None:
        if raw is None:
            return None
        val = " ".join(raw.strip().split())
        return val if val else None

    def _build_polars_df(
        self, sede_key: str, report_key: str, rep_date: date, csv_path: Path
    ) -> pl.DataFrame:
        schema = TRACKING_POLARS_SCHEMA if report_key == "tracking" else TRANSACTIONS_POLARS_SCHEMA
        raw_text = csv_path.read_text(encoding="utf-8-sig", errors="replace")
        all_rows = list(csv.reader(raw_text.splitlines()))

        if len(all_rows) <= 1:
            self.log.warning(f"[{sede_key.upper()} - {report_key.upper()}] Archivo sin filas: {csv_path.name}")
            return pl.DataFrame(schema=schema)

        raw_headers = [h.strip() for h in all_rows[0]]
        data_rows = [r for r in all_rows[1:] if any(cell.strip() for cell in r)]
        if not data_rows:
            return pl.DataFrame(schema=schema)

        header_map = TRACKING_HEADER_MAP if report_key == "tracking" else TRANSACTIONS_HEADER_MAP
        canonical_headers = [header_map.get(h, "") for h in raw_headers]

        unmapped = [h for h, c in zip(raw_headers, canonical_headers) if not c]
        if unmapped:
            raise ValueError(f"Columnas desconocidas en {csv_path.name}: {unmapped}")

        date_fields = {"entry_date", "payment_date", "exit_date"}
        date_indices = [i for i, c in enumerate(canonical_headers) if c in date_fields]
        csv_lang = self._detect_csv_language(raw_headers, data_rows, date_indices)

        int_fields = {
            "area_id",
            "t_total_number",
            "paid_equipment_number",
            "entry_equipment_number",
            "exit_equipment_number",
        }
        zero_float_fields = {
            "parking_fee",
            "payment",
            "credit",
            "cash_sales",
            "credit_sales",
            "disc_total",
            "misc_sales",
        }
        nullable_float_fields = {
            *(f"discount_{i}" for i in range(1, 10)),
            "fiscal_amount_1",
            "fiscal_amount_2",
            "fiscal_amount_3",
        }

        sanitized_records: list[dict[str, object]] = []
        for raw_row in data_rows:
            padded = raw_row + [""] * (len(canonical_headers) - len(raw_row))
            raw_dict = dict(zip(canonical_headers, padded))

            clean_row: dict[str, object] = {}
            for col in schema:
                if col == "sede":
                    clean_row[col] = sede_key
                elif col == "fecha_reporte":
                    clean_row[col] = rep_date
                elif col == "archivo_origen":
                    clean_row[col] = csv_path.name
                elif col in date_fields:
                    clean_row[col] = self._parse_exact_datetime(raw_dict.get(col), csv_lang)
                elif col in int_fields:
                    clean_row[col] = self._parse_exact_int(raw_dict.get(col))
                elif col in zero_float_fields:
                    clean_row[col] = self._parse_exact_float(raw_dict.get(col), csv_lang, default_zero=True)
                elif col in nullable_float_fields:
                    clean_row[col] = self._parse_exact_float(raw_dict.get(col), csv_lang, default_zero=False)
                else:
                    clean_row[col] = self._clean_text(raw_dict.get(col))

            sanitized_records.append(clean_row)

        df = pl.DataFrame(sanitized_records, schema=schema)

        truncate_exprs = [
            pl.col(col).str.slice(0, max_len).alias(col)
            for col, max_len in AMANO_JP_MAX_LENGTHS.items()
            if col in df.columns
        ]
        if truncate_exprs:
            df = df.with_columns(truncate_exprs)

        self.log.info(
            f"[{sede_key.upper()} - {report_key.upper()}] DataFrame sanitizado: {df.height} filas "
            f"(idioma CSV={csv_lang}, archivo={csv_path.name})"
        )
        return df

    def transform(self, files: list[Path]) -> list[tuple[str, str, str, pl.DataFrame]]:
        batches: list[tuple[str, str, str, pl.DataFrame]] = []

        if not self._batch_items and files:
            for f in files:
                sede_key, report_key, rep_date = self._infer_file_metadata(f)
                self._batch_items.append((sede_key, report_key, rep_date, f))

        for sede_key, report_key, rep_date, csv_path in self._batch_items:
            df = self._build_polars_df(sede_key, report_key, rep_date, csv_path)
            batches.append((sede_key, report_key, rep_date.isoformat(), df))

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

            table_name = (
                "amano_japon_tracking"
                if report_key == "tracking"
                else "amano_japon_transactions"
            )
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