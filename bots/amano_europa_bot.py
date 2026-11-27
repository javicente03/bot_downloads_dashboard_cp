import csv
from datetime import datetime, timedelta
from pathlib import Path
import re
import unicodedata
import polars as pl
from playwright.async_api import Locator, Page
from config.settings import settings
from core.base_bot import BaseBot
from core.browser import BrowserManager
from core.database import SQLServerManager


REPORTS_CONFIG: dict[str, dict[str, str]] = {
    "tickets": {
        "label": "Tickets",
        "path": "/xoffice/index.php?mod=report&page=ticketinformationlist&menu_select=1",
        "table": "amano_europa_tickets",
        "date_col": "fecha_reporte",
    },
    "ventas": {
        "label": "Ventas / Pagos",
        "path": "/xoffice/index.php?mod=report&page=statpayment&menu_select=1",
        "table": "amano_europa_ventas",
        "date_col": "fecha_reporte",
    },
    "descuentos": {
        "label": "Descuentos",
        "path": "/xoffice/index.php?mod=report&page=salesdiscount&menu_select=1",
        "table": "amano_europa_descuentos",
        "date_col": "fecha_reporte",
    },
}

# Mapa (sede -> reporte -> (start_input_id, end_input_id)) en XOffice
DATE_INPUTS_CONFIG: dict[str, dict[str, tuple[str, str]]] = {
    "pichimapu": {
        "ventas": ("84783654c993bddf5c10b0be2e250058_date", "d510f9ac8a8008c4da2d2e36f7840e1e_date"),
        "tickets": ("26486473f3d59ae7bc7b86b9e4390ea2_date", "54d5f1898139aafd330a84ae3e1edf31_date"),
        "descuentos": ("3dab292151dd7c9f52c2bdd42c993710_date", "1362f0581e7a2a359cf28918b76b04b0_date"),
    },
    "indisa": {
        "ventas": ("84783654c993bddf5c10b0be2e250058_date", "d510f9ac8a8008c4da2d2e36f7840e1e_date"),
        "tickets": ("26486473f3d59ae7bc7b86b9e4390ea2_date", "54d5f1898139aafd330a84ae3e1edf31_date"),
        "descuentos": ("3dab292151dd7c9f52c2bdd42c993710_date", "1362f0581e7a2a359cf28918b76b04b0_date"),
    },
    "recoleta": {
        "ventas": ("968d00eb938e673ff9dba3e14e8dfe0a_date", "6e23be3e195c1150d80ce2457ae8bbd0_date"),
        "tickets": ("26486473f3d59ae7bc7b86b9e4390ea2_date", "54d5f1898139aafd330a84ae3e1edf31_date"),
        "descuentos": ("3dab292151dd7c9f52c2bdd42c993710_date", "1362f0581e7a2a359cf28918b76b04b0_date"),
    },
}

TABLE_COLUMNS: dict[str, list[str]] = {
    "amano_europa_tickets": [
        "sede", "fecha_reporte", "ticket", "contrato", "perfil_acceso", "tipo_tarjeta", "producto",
        "entrada", "hora_entrada", "matricula", "salida", "hora_salida",
        "cajero_automatico", "hora_pago", "importe_pagar", "duracion", "eventos",
        "numero_tarjeta", "nombre", "apellido",
    ],
    "amano_europa_ventas": [
        "sede", "fecha_reporte", "fecha_pago", "dispositivo", "tipo_venta", "hora_entrada", "hora_salida",
        "tarifa", "descuento_monto", "importe_total", "pagado", "vuelto",
        "pagado_neto_cambio", "valor_iva", "neto", "tipo_pago", "subtipo_pago",
        "observaciones", "numero_tarjeta", "transbank", "codigo_mantenimiento",
        "usuario", "turno", "numero_recibo", "recibo_fiscal", "ticket",
        "nombre_conductor", "matricula", "producto", "articulo", "tipo_tarjeta",
        "perfil_acceso", "descuento_nombre", "tienda_numero", "descuento_numero",
    ],
    "amano_europa_descuentos": [
        "sede", "fecha_reporte", "hora_pago", "dispositivo", "cliente", "contrato", "descuento",
        "tipo_valor", "importe", "codigo_descuento", "tienda_numero", "descuento_numero",
        "numero_recibo", "ticket", "entrada", "hora_entrada", "matricula",
        "perfil_acceso", "tipo_tarjeta", "producto",
    ],
}

DATETIME_COLS = {"hora_entrada", "hora_salida", "hora_pago", "fecha_pago"}
DECIMAL_COLS = {
    "importe_pagar", "tarifa", "descuento_monto", "importe_total",
    "pagado", "vuelto", "pagado_neto_cambio", "valor_iva", "neto", "importe",
}

COLUMN_MAX_LENGTHS: dict[str, int] = {
    "sede": 30,
    "duracion": 30,
    "matricula": 30,
    "tipo_valor": 30,
    "ticket": 50,
    "codigo_mantenimiento": 50,
    "turno": 50,
    "numero_recibo": 50,
    "recibo_fiscal": 50,
    "tienda_numero": 50,
    "descuento_numero": 50,
    "codigo_descuento": 50,
    "contrato": 100,
    "perfil_acceso": 100,
    "tipo_tarjeta": 100,
    "producto": 100,
    "entrada": 100,
    "salida": 100,
    "cajero_automatico": 100,
    "numero_tarjeta": 100,
    "nombre": 100,
    "apellido": 100,
    "dispositivo": 100,
    "tipo_venta": 100,
    "tipo_pago": 100,
    "subtipo_pago": 100,
    "transbank": 100,
    "usuario": 100,
    "nombre_conductor": 100,
    "articulo": 100,
    "cliente": 100,
    "descuento_nombre": 150,
    "descuento": 150,
    "eventos": 255,
    "observaciones": 255,
}


def _slugify_header(text_val: str) -> str:
    """Convierte 'Nº. de Matrícula' -> 'no_de_matricula' de forma determinista."""
    clean = unicodedata.normalize("NFKD", text_val).encode("ascii", "ignore").decode("ascii")
    clean = clean.lower().strip()
    out = [ch if ch.isalnum() else "_" for ch in clean]
    return "_".join(part for part in "".join(out).split("_") if part)


class AmanoEuropaBot(BaseBot):
    name = "amano_europa"
    description = "Descarga e ingesta informes CSV de Amano Europa / XOffice (Tickets, Ventas, Descuentos) hacia SQL Server"

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        self._batch_items: list[tuple[str, str, Path]] = []

    def _resolve_sites(self) -> list[tuple[str, dict[str, str]]]:
        sede_param = self.params.get("sede", "todas").lower().strip()
        all_sites = settings.amano_europa_sites

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

    async def _format_xoffice_date(self, locator: Locator, target_date: datetime) -> str:
        custom_fmt = self.params.get("date_fmt", "").strip()
        if custom_fmt:
            return target_date.strftime(custom_fmt)

        meta = await locator.evaluate(
            """el => {
                let jqFmt = '';
                if (window.jQuery && window.jQuery(el).data('datepicker')) {
                    try {
                        jqFmt = window.jQuery(el).datepicker('option', 'dateFormat') || '';
                    } catch (e) {}
                }
                return {
                    val: el.value || '',
                    placeholder: el.getAttribute('placeholder') || '',
                    jqFmt: jqFmt,
                };
            }"""
        )
        sample = meta["val"] or meta["placeholder"]
        jq_fmt = meta["jqFmt"].lower()

        if re.match(r"^\d{4}-\d{2}-\d{2}", sample) or jq_fmt.startswith("yy-"):
            return target_date.strftime("%Y-%m-%d")
        if "/" in sample or "/" in jq_fmt:
            return target_date.strftime("%d/%m/%Y")
        return target_date.strftime("%d-%m-%Y")

    async def _set_xoffice_date(self, locator: Locator, date_str: str) -> None:
        await locator.wait_for(state="visible")
        await locator.fill(date_str)
        await locator.evaluate(
            """(el, val) => {
                el.value = val;
                if (window.jQuery && window.jQuery(el).data('datepicker')) {
                    try {
                        window.jQuery(el).datepicker('setDate', val);
                        window.jQuery(el).datepicker('hide');
                    } catch (e) {}
                }
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new Event('blur', { bubbles: true }));
            }""",
            date_str,
        )

    async def _login(self, page: Page, base_url: str, user: str, password: str) -> None:
        login_url = f"{base_url}/xoffice/index.php"
        self.log.info(f"Accediendo a {login_url}...")
        await page.goto(login_url, wait_until="domcontentloaded")

        await page.wait_for_selector("#username", state="visible")
        await page.fill("#username", user)
        await page.fill("#password", password)

        self.log.info("Enviando credenciales...")
        async with page.expect_navigation(wait_until="networkidle"):
            await page.press("#password", "Enter")

        if await page.locator("#username").is_visible():
            raise RuntimeError(f"Login fallido en {base_url}. Verifica usuario y contraseña en .env.")

        self.log.success("Sesión iniciada correctamente.")

    async def _download_report(
        self,
        page: Page,
        sede_key: str,
        base_url: str,
        report_key: str,
        report_info: dict[str, str],
        target_date: datetime,
    ) -> Path:
        full_url = f"{base_url}{report_info['path']}"
        self.log.info(f"[{sede_key.upper()}] Navegando a {report_info['label']}...")
        await page.goto(full_url, wait_until="networkidle")

        start_id, end_id = DATE_INPUTS_CONFIG[sede_key][report_key]
        start_input = page.locator(f'[id="{start_id}"]')
        end_input = page.locator(f'[id="{end_id}"]')

        await start_input.wait_for(state="visible")
        await end_input.wait_for(state="visible")

        date_str = await self._format_xoffice_date(start_input, target_date)
        self.log.info(f"[{sede_key.upper()}] Aplicando rango de fecha: {date_str} -> {date_str}")

        await self._set_xoffice_date(start_input, date_str)
        await self._set_xoffice_date(end_input, date_str)
        await page.wait_for_timeout(300)

        # Clic en "Buscar" (#obj_2)
        await page.click("#obj_2")
        await page.wait_for_load_state("networkidle")

        await page.wait_for_selector("a#ref_1", state="visible")
        context = page.context
        pages_before = len(context.pages)

        await page.click("a#ref_1")
        await page.wait_for_timeout(1000)

        if len(context.pages) > pages_before:
            export_page = context.pages[-1]
            await export_page.wait_for_load_state("domcontentloaded")
            is_popup = True
        else:
            export_page = page
            await export_page.wait_for_load_state("domcontentloaded")
            is_popup = False

        try:
            await export_page.wait_for_selector("#format", state="visible")
            async with export_page.expect_navigation(wait_until="networkidle"):
                await export_page.select_option("#format", value="csv")

            await export_page.wait_for_selector("#obj_4", state="visible")
            async with export_page.expect_download() as download_info:
                await export_page.click("#obj_4")

            download = await download_info.value
            date_folder = target_date.strftime("%Y-%m-%d")
            filename = f"{sede_key}_{report_key}_{date_folder}.csv"
            saved_path = await BrowserManager.save_download(
                download=download,
                target_dir=self.download_dir / date_folder / sede_key,
                custom_name=filename,
            )
            return saved_path
        finally:
            if is_popup and not export_page.is_closed():
                await export_page.close()

    def _discover_local_files(self, local_dir: Path) -> list[Path]:
        if not local_dir.exists():
            raise FileNotFoundError(f"La carpeta local no existe: {local_dir}")

        allowed_sites = {k for k, _ in self._resolve_sites()}
        allowed_reports = {k for k, _ in self._resolve_reports()}

        files: list[Path] = []
        for path in sorted(local_dir.rglob("*.csv")):
            fname = path.stem.lower()
            sede_key = next((k for k in ("pichimapu", "indisa", "recoleta") if k in fname), None)
            report_key = next((k for k in ("tickets", "ventas", "descuentos") if k in fname), None)
            if not (sede_key and report_key):
                self.log.warning(f"Archivo ignorado (no identifica sede/reporte en nombre): {path.name}")
                continue
            if sede_key not in allowed_sites or report_key not in allowed_reports:
                continue

            self._batch_items.append((sede_key, report_key, path))
            files.append(path)
        return files

    async def _dump_debug_screenshot(self, page: Page, sede_key: str) -> None:
        if page.is_closed():
            return
        shot_path = self.download_dir / f"debug_{sede_key}.png"
        await page.screenshot(path=str(shot_path), full_page=True)
        self.log.warning(f"[{sede_key.upper()}] Captura de depuración guardada en: {shot_path}")

    async def extract(self) -> list[Path]:
        self._batch_items.clear()

        local_dir = self.params.get("local_dir", "").strip()
        if local_dir:
            local_path = Path(local_dir)
            self.log.info(f"Cargando archivos locales desde: {local_path}")
            return self._discover_local_files(local_path)

        sites = self._resolve_sites()
        reports = self._resolve_reports()
        target_date = self._resolve_target_date()
        target_date_iso = target_date.strftime("%Y-%m-%d")
        downloaded_files: list[Path] = []

        headless_param = self.params.get("headless")
        headless = None if headless_param is None else headless_param.lower() == "true"

        for sede_key, site in sites:
            self.log.info(f"=== Procesando sede: {site['nombre']} ({site['base_url']}) ===")
            if not site["user"] or not site["password"]:
                msg = f"Credenciales faltantes en .env para '{sede_key}'."
                self.log.error(msg)
                for report_key, _ in reports:
                    self.record_error(sede_key, report_key, target_date_iso, msg)
                    SQLServerManager.log_execution(
                        bot_name=self.name,
                        sede=sede_key,
                        reporte=report_key,
                        fecha_reporte=target_date_iso,
                        filas_insertadas=0,
                        estado="ERROR",
                        mensaje_error=msg,
                    )
                continue

            completed_reports: set[str] = set()
            try:
                async with BrowserManager.get_page(headless=headless) as page:
                    try:
                        await self._login(page, site["base_url"], site["user"], site["password"])

                        for report_key, report_info in reports:
                            report_page = await page.context.new_page()
                            report_page.set_default_timeout(settings.DOWNLOAD_TIMEOUT_MS)
                            try:
                                file_path = await self._download_report(
                                    page=report_page,
                                    sede_key=sede_key,
                                    base_url=site["base_url"],
                                    report_key=report_key,
                                    report_info=report_info,
                                    target_date=target_date,
                                )
                                self._batch_items.append((sede_key, report_key, file_path))
                                downloaded_files.append(file_path)
                                completed_reports.add(report_key)
                            except Exception as rep_exc:
                                await self._dump_debug_screenshot(report_page, f"{sede_key}_{report_key}")
                                self.log.error(
                                    f"[{sede_key.upper()} - {report_key.upper()}] Error en reporte: {rep_exc}"
                                )
                                self.record_error(sede_key, report_key, target_date_iso, str(rep_exc))
                                SQLServerManager.log_execution(
                                    bot_name=self.name,
                                    sede=sede_key,
                                    reporte=report_key,
                                    fecha_reporte=target_date_iso,
                                    filas_insertadas=0,
                                    estado="ERROR",
                                    mensaje_error=str(rep_exc),
                                )
                                completed_reports.add(report_key)
                            finally:
                                for p in list(page.context.pages):
                                    if p != page and not p.is_closed():
                                        await p.close()
                    except Exception:
                        await self._dump_debug_screenshot(page, sede_key)
                        raise
            except Exception as exc:
                self.log.error(f"[{sede_key.upper()}] Error de conexión/sesión en sede: {exc}")
                for report_key, _ in reports:
                    if report_key in completed_reports:
                        continue
                    self.record_error(sede_key, report_key, target_date_iso, str(exc))
                    SQLServerManager.log_execution(
                        bot_name=self.name,
                        sede=sede_key,
                        reporte=report_key,
                        fecha_reporte=target_date_iso,
                        filas_insertadas=0,
                        estado="ERROR",
                        mensaje_error=str(exc),
                    )

        return downloaded_files

    def _read_clean_csv(self, file_path: Path) -> pl.DataFrame:
        raw_bytes = file_path.read_bytes()
        try:
            content = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            content = raw_bytes.decode("latin-1")

        lines = [line for line in content.splitlines() if line.strip()]
        if len(lines) <= 1:
            return pl.DataFrame()

        reader = csv.reader(lines, delimiter=";", quotechar='"')
        raw_headers = next(reader, [])

        while raw_headers and raw_headers[-1].strip() == "":
            raw_headers.pop()

        seen: dict[str, int] = {}
        headers: list[str] = []
        for h in raw_headers:
            slug = _slugify_header(h) or "col"
            count = seen.get(slug, 0) + 1
            seen[slug] = count
            headers.append(slug if count == 1 else f"{slug}_{count}")

        num_cols = len(headers)
        rows: list[list[str | None]] = []
        for row in reader:
            if not any(cell.strip() for cell in row):
                continue
            normalized_row = [
                (cell.strip() if cell.strip() != "" else None)
                for cell in row[:num_cols]
            ]
            while len(normalized_row) < num_cols:
                normalized_row.append(None)
            rows.append(normalized_row)

        if not rows:
            return pl.DataFrame()

        return pl.DataFrame(rows, schema={h: pl.Utf8 for h in headers}, orient="row")

    @staticmethod
    def _parse_dates(df: pl.DataFrame, cols: list[str]) -> pl.DataFrame:
        exprs = []
        for col in cols:
            if col in df.columns:
                exprs.append(
                    pl.coalesce([
                        pl.col(col).str.strptime(pl.Datetime("us"), format="%d-%m-%Y %H:%M:%S", strict=False),
                        pl.col(col).str.strptime(pl.Datetime("us"), format="%d-%m-%Y %H:%M", strict=False),
                        pl.col(col).str.strptime(pl.Datetime("us"), format="%Y-%m-%d %H:%M:%S", strict=False),
                    ]).alias(col)
                )
        return df.with_columns(exprs) if exprs else df

    @staticmethod
    def _parse_decimals(df: pl.DataFrame, cols: list[str]) -> pl.DataFrame:
        exprs = []
        for col in cols:
            if col in df.columns:
                exprs.append(
                    pl.col(col)
                    .str.replace_all(r"\.", "")
                    .str.replace(",", ".")
                    .cast(pl.Float64, strict=False)
                    .alias(col)
                )
        return df.with_columns(exprs) if exprs else df

    def _align_to_table(
        self, df: pl.DataFrame, table_name: str, sede_key: str, report_date: str
    ) -> pl.DataFrame:
        report_date_obj = datetime.strptime(report_date, "%Y-%m-%d").date()
        df = df.with_columns([
            pl.lit(sede_key).cast(pl.Utf8).alias("sede"),
            pl.lit(report_date_obj).cast(pl.Date).alias("fecha_reporte"),
        ])
        target_cols = TABLE_COLUMNS[table_name]
        missing_exprs = []
        for col in target_cols:
            if col not in df.columns:
                if col in DATETIME_COLS:
                    dtype = pl.Datetime("us")
                elif col in DECIMAL_COLS:
                    dtype = pl.Float64
                else:
                    dtype = pl.Utf8
                missing_exprs.append(pl.lit(None).cast(dtype).alias(col))

        if missing_exprs:
            df = df.with_columns(missing_exprs)

        cast_nulls = [
            pl.col(c).cast(pl.Utf8)
            for c in target_cols
            if df[c].dtype == pl.Null
        ]
        if cast_nulls:
            df = df.with_columns(cast_nulls)

        truncate_exprs = [
            pl.col(c).str.slice(0, COLUMN_MAX_LENGTHS[c]).alias(c)
            for c in target_cols
            if c in COLUMN_MAX_LENGTHS and df[c].dtype == pl.Utf8
        ]
        if truncate_exprs:
            df = df.with_columns(truncate_exprs)

        return df.select(target_cols)

    def _normalize_tickets(self, df: pl.DataFrame, sede_key: str, report_date: str) -> pl.DataFrame:
        rename_map = {
            "perfil_de_acceso": "perfil_acceso",
            "tipo_de_tarjeta": "tipo_tarjeta",
            "hora_de_entrada": "hora_entrada",
            "no_de_matricula": "matricula",
            "hora_de_salida": "hora_salida",
            "hora_de_pago": "hora_pago",
            "importe_a_pagar": "importe_pagar",
            "no_de_tarjeta": "numero_tarjeta",
        }
        df = df.rename({k: v for k, v in rename_map.items() if k in df.columns})
        df = self._parse_dates(df, ["hora_entrada", "hora_salida", "hora_pago"])
        df = self._parse_decimals(df, ["importe_pagar"])
        return self._align_to_table(df, "amano_europa_tickets", sede_key, report_date)

    def _normalize_descuentos(self, df: pl.DataFrame, sede_key: str, report_date: str) -> pl.DataFrame:
        rename_map = {
            "hora_de_pago": "hora_pago",
            "tipo_de_valor": "tipo_valor",
            "codigo_de_descuento": "codigo_descuento",
            "descuento_no": "descuento_numero",
            "no_de_recibo": "numero_recibo",
            "hora_de_entrada": "hora_entrada",
            "no_de_matricula": "matricula",
            "perfil_de_acceso": "perfil_acceso",
            "tipo_de_tarjeta": "tipo_tarjeta",
        }
        df = df.rename({k: v for k, v in rename_map.items() if k in df.columns})
        df = self._parse_dates(df, ["hora_pago", "hora_entrada"])
        df = self._parse_decimals(df, ["importe"])
        return self._align_to_table(df, "amano_europa_descuentos", sede_key, report_date)

    def _normalize_pagos(self, df: pl.DataFrame, sede_key: str, report_date: str) -> pl.DataFrame:
        rename_map = {
            "fecha": "fecha_pago",
            "sello_de_tiempo": "fecha_pago",
            "tipo_de_venta": "tipo_venta",
            "hora_de_entrada": "hora_entrada",
            "hora_de_salida": "hora_salida",
            "descuento": "descuento_monto",
            "descuento_2": "descuento_nombre",
            "importe_total_a_pagar": "importe_total",
            "dinero_de_cambio": "vuelto",
            "pagado_dinero_de_cambio": "pagado_neto_cambio",
            "valor_i_v_a": "valor_iva",
            "tipo_de_pago": "tipo_pago",
            "subtipo_de_pago": "subtipo_pago",
            "eventos": "observaciones",
            "no_de_tarjeta": "numero_tarjeta",
            "codigo_de_mantenimiento": "codigo_mantenimiento",
            "no_de_recibo": "numero_recibo",
            "recibo": "numero_recibo",
            "no_de_ticket": "ticket",
            "nombre_del_conductor": "nombre_conductor",
            "no_de_matricula": "matricula",
            "tipo_de_tarjeta": "tipo_tarjeta",
            "perfil_de_acceso": "perfil_acceso",
            "descuento_no": "descuento_numero",
        }
        df = df.rename({k: v for k, v in rename_map.items() if k in df.columns})
        df = self._parse_dates(df, ["fecha_pago", "hora_entrada", "hora_salida"])
        df = self._parse_decimals(
            df,
            [
                "tarifa",
                "descuento_monto",
                "importe_total",
                "pagado",
                "vuelto",
                "pagado_neto_cambio",
                "valor_iva",
                "neto",
            ],
        )
        return self._align_to_table(df, "amano_europa_ventas", sede_key, report_date)

    def _infer_report_date(self, file_path: Path) -> str:
        """Extrae YYYY-MM-DD del nombre o carpeta del archivo o usa ayer por defecto."""
        fecha_param = self.params.get("fecha", "").strip()
        if fecha_param:
            return datetime.strptime(fecha_param, "%Y-%m-%d").strftime("%Y-%m-%d")

        match = re.search(r"(\d{4}-\d{2}-\d{2})", file_path.name) or re.search(
            r"(\d{4}-\d{2}-\d{2})", str(file_path.parent)
        )
        if match:
            return match.group(1)

        return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    def transform(self, files: list[Path]) -> list[tuple[str, str, str, pl.DataFrame]]:
        batches: list[tuple[str, str, str, pl.DataFrame]] = []

        if not self._batch_items and files:
            for path in files:
                fname = path.stem.lower()
                sede_key = next((k for k in ("pichimapu", "indisa", "recoleta") if k in fname), None)
                report_key = next((k for k in ("tickets", "ventas", "descuentos") if k in fname), None)
                if sede_key and report_key:
                    self._batch_items.append((sede_key, report_key, path))

        for sede_key, report_key, file_path in self._batch_items:
            self.log.info(f"[{sede_key.upper()} - {report_key.upper()}] Procesando {file_path.name}...")
            report_date = self._infer_report_date(file_path)
            raw_df = self._read_clean_csv(file_path)

            if raw_df.is_empty():
                self.log.warning(f"[{sede_key.upper()} - {report_key.upper()}] Archivo sin datos.")
                batches.append((sede_key, report_key, report_date, pl.DataFrame()))
                continue

            if report_key == "tickets":
                clean_df = self._normalize_tickets(raw_df, sede_key, report_date)
            elif report_key == "ventas":
                clean_df = self._normalize_pagos(raw_df, sede_key, report_date)
            elif report_key == "descuentos":
                clean_df = self._normalize_descuentos(raw_df, sede_key, report_date)
            else:
                continue

            batches.append((sede_key, report_key, report_date, clean_df))

        return batches

    def load(self, batches: list[tuple[str, str, str, pl.DataFrame]]) -> int:
        if not batches:
            return 0

        SQLServerManager.check_connection()
        total_inserted = 0

        for sede_key, report_key, report_date, clean_df in batches:
            if clean_df.is_empty():
                SQLServerManager.log_execution(
                    bot_name=self.name,
                    sede=sede_key,
                    reporte=report_key,
                    fecha_reporte=report_date,
                    filas_insertadas=0,
                    estado="SIN_DATOS",
                )
                continue

            table_name = REPORTS_CONFIG[report_key]["table"]
            inserted = SQLServerManager.replace_by_sede_and_dates(
                df=clean_df,
                table_name=table_name,
                sede=sede_key,
                date_column="fecha_reporte",
            )
            total_inserted += inserted
            SQLServerManager.log_execution(
                bot_name=self.name,
                sede=sede_key,
                reporte=report_key,
                fecha_reporte=report_date,
                filas_insertadas=inserted,
                estado="OK",
            )

        return total_inserted