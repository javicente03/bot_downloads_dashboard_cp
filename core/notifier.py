from datetime import datetime
from email.message import EmailMessage
import html
import smtplib
import ssl
from config.settings import settings
from core.logger import get_logger

log = get_logger("NOTIFIER")

EXTERNAL_ERROR_TOKENS = (
    "timeout",
    "timed out",
    "err_connection",
    "err_name_not_resolved",
    "err_network",
    "err_internet",
    "err_ssl",
    "err_empty_response",
    "target page, context or browser has been closed",
    "navigation failed",
    "net::",
    "502 bad gateway",
    "503 service",
    "504 gateway",
    "login fallido",
    "08s01",
    "08001",
    "hyt00",
    "hyt01",
    "communication link failure",
    "login timeout expired",
    "no estuvo lista tras",
    "reportó error generando",
)


def classify_error(error_msg: str | None) -> tuple[bool, str]:
    """Determina si el fallo es externo (red/portal/VPN) o interno."""
    msg = (error_msg or "").lower()
    if any(token in msg for token in EXTERNAL_ERROR_TOKENS):
        return True, "EXTERNO (Portal / Red / Timeout)"
    return False, "INTERNO (Datos / Parsing / BD)"


class SMTPNotifier:
    @staticmethod
    def _dispatch_email(subject: str, plain_body: str, html_body: str) -> bool:
        if not settings.SMTP_ENABLED:
            log.info("SMTP_ENABLED=false. Se omite el envío de correo.")
            return False

        recipients = settings.smtp_recipients
        if not settings.SMTP_HOST or not recipients:
            log.warning("SMTP_HOST o SMTP_TO no configurados en .env. No se envió correo.")
            return False

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
        msg["To"] = ", ".join(recipients)
        msg.set_content(plain_body)
        msg.add_alternative(html_body, subtype="html")

        try:
            log.info(f"Enviando informe SMTP a {', '.join(recipients)}...")
            if settings.SMTP_USE_SSL:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, context=context, timeout=25) as server:
                    if settings.SMTP_USER:
                        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=25) as server:
                    server.ehlo()
                    if settings.SMTP_USE_TLS:
                        server.starttls(context=ssl.create_default_context())
                        server.ehlo()
                    if settings.SMTP_USER:
                        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                    server.send_message(msg)

            log.success("Correo enviado correctamente.")
            return True
        except Exception as exc:
            log.error(f"No se pudo enviar el correo SMTP: {exc}")
            return False

    @staticmethod
    def send_execution_report(
        window_start: str,
        window_end: str,
        total_expected: int,
        already_ok_count: int,
        resolved_items: list[dict[str, object]],
        unresolved_items: list[dict[str, str]],
        duration_seconds: float,
    ) -> bool:
        """
        Envía siempre un informe consolidado al finalizar auto-sync:
          - Verde (OK) si unresolved_items está vacío (siempre que SMTP_SEND_ON_SUCCESS=true).
          - Rojo/Ámbar (ALERTA) si quedaron reportes pendientes o con error.
        """
        has_failures = len(unresolved_items) > 0

        if not has_failures and not settings.SMTP_SEND_ON_SUCCESS:
            log.info("Ejecución 100% OK y SMTP_SEND_ON_SUCCESS=false. No se envía correo.")
            return False

        enriched_failures: list[dict[str, str | bool]] = []
        for item in unresolved_items:
            is_ext, category = classify_error(item.get("mensaje_error"))
            enriched_failures.append({**item, "is_external": is_ext, "categoria": category})

        if has_failures and settings.SMTP_ONLY_EXTERNAL:
            external_only = [e for e in enriched_failures if e["is_external"]]
            if not external_only and not settings.SMTP_SEND_ON_SUCCESS:
                log.info("Solo hubo errores internos y SMTP_ONLY_EXTERNAL=true. No se envía correo.")
                return False

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_rows_inserted = sum(int(r.get("filas_insertadas") or 0) for r in resolved_items)

        if has_failures:
            external_count = sum(1 for e in enriched_failures if e["is_external"])
            subject = (
                f"[ALERTA ETL PARKING] {len(unresolved_items)} pendiente(s) | "
                f"{len(resolved_items)} completado(s) ({window_start} -> {window_end})"
            )
            header_color = "#b91c1c"
            status_banner = (
                f"ATENCIÓN: Quedaron {len(unresolved_items)} reporte(s) sin completar "
                f"({external_count} externo(s)). Se reintentarán automáticamente en la próxima corrida."
            )
        else:
            subject = (
                f"[OK ETL PARKING] Sincronización completada | "
                f"{len(resolved_items)} procesado(s) ({total_rows_inserted:,} filas) — {window_end}"
            )
            header_color = "#15803d"
            status_banner = (
                "TODOS LOS REPORTES AL DÍA: No quedaron fechas ni sucursales pendientes en la ventana."
            )

        # 1. Texto plano
        plain_lines = [
            f"Informe de Ejecución ETL Parking - {now_str}",
            f"Ventana auditada: {window_start} -> {window_end} | Duración: {duration_seconds:.1f}s",
            status_banner,
            "",
            f"Resumen: Esperados={total_expected} | Ya al día={already_ok_count} | "
            f"Procesados ahora={len(resolved_items)} ({total_rows_inserted} filas) | "
            f"Pendientes/Error={len(unresolved_items)}",
        ]

        if enriched_failures:
            plain_lines.extend(["", "=== PENDIENTES / ERRORES ==="])
            for e in enriched_failures:
                plain_lines.append(
                    f"- [{e['fecha_reporte']}] {e['bot_name']} | {e['sede']} | {e['reporte']} | "
                    f"{e['categoria']} -> {e.get('mensaje_error') or 'Sin completar'}"
                )

        if resolved_items:
            plain_lines.extend(["", "=== PROCESADOS EN ESTA EJECUCIÓN ==="])
            for r in resolved_items:
                plain_lines.append(
                    f"- [{r['fecha_reporte']}] {r['bot_name']} | {r['sede']} | {r['reporte']} -> "
                    f"{r['estado']} ({r.get('filas_insertadas', 0)} filas)"
                )

        # 2. HTML
        failures_section_html = ""
        if enriched_failures:
            fail_rows = []
            for e in enriched_failures:
                badge_bg = "#fde8e8" if e["is_external"] else "#fef3c7"
                badge_fg = "#9b1c1c" if e["is_external"] else "#92400e"
                err_text = html.escape((e.get("mensaje_error") or "Pendiente sin registro")[:280])
                fail_rows.append(f"""
                    <tr>
                        <td style="padding:7px;border:1px solid #e5e7eb;white-space:nowrap;"><strong>{html.escape(str(e['fecha_reporte']))}</strong></td>
                        <td style="padding:7px;border:1px solid #e5e7eb;">{html.escape(str(e['bot_name']))}</td>
                        <td style="padding:7px;border:1px solid #e5e7eb;">{html.escape(str(e['sede']))}</td>
                        <td style="padding:7px;border:1px solid #e5e7eb;">{html.escape(str(e['reporte']))}</td>
                        <td style="padding:7px;border:1px solid #e5e7eb;">
                            <span style="background:{badge_bg};color:{badge_fg};padding:2px 6px;border-radius:4px;font-size:11px;font-weight:bold;">
                                {html.escape(str(e['categoria']))}
                            </span>
                        </td>
                        <td style="padding:7px;border:1px solid #e5e7eb;font-family:monospace;font-size:12px;">{err_text}</td>
                    </tr>
                """)
            failures_section_html = f"""
                <h3 style="color:#b91c1c;margin-top:20px;margin-bottom:8px;">Reportes Pendientes / con Error ({len(enriched_failures)})</h3>
                <table style="border-collapse:collapse;width:100%;font-size:13px;">
                  <thead>
                    <tr style="background:#fef2f2;text-align:left;">
                      <th style="padding:7px;border:1px solid #e5e7eb;">Fecha</th>
                      <th style="padding:7px;border:1px solid #e5e7eb;">Robot</th>
                      <th style="padding:7px;border:1px solid #e5e7eb;">Sede</th>
                      <th style="padding:7px;border:1px solid #e5e7eb;">Reporte</th>
                      <th style="padding:7px;border:1px solid #e5e7eb;">Tipo Fallo</th>
                      <th style="padding:7px;border:1px solid #e5e7eb;">Detalle</th>
                    </tr>
                  </thead>
                  <tbody>{''.join(fail_rows)}</tbody>
                </table>
            """

        resolved_section_html = ""
        if resolved_items:
            ok_rows = []
            for r in resolved_items:
                st = str(r.get("estado", "OK"))
                st_bg = "#dcfce7" if st == "OK" else "#f3f4f6"
                st_fg = "#166534" if st == "OK" else "#374151"
                ok_rows.append(f"""
                    <tr>
                        <td style="padding:7px;border:1px solid #e5e7eb;white-space:nowrap;">{html.escape(str(r['fecha_reporte']))}</td>
                        <td style="padding:7px;border:1px solid #e5e7eb;">{html.escape(str(r['bot_name']))}</td>
                        <td style="padding:7px;border:1px solid #e5e7eb;">{html.escape(str(r['sede']))}</td>
                        <td style="padding:7px;border:1px solid #e5e7eb;">{html.escape(str(r['reporte']))}</td>
                        <td style="padding:7px;border:1px solid #e5e7eb;">
                            <span style="background:{st_bg};color:{st_fg};padding:2px 6px;border-radius:4px;font-size:11px;font-weight:bold;">
                                {html.escape(st)}
                            </span>
                        </td>
                        <td style="padding:7px;border:1px solid #e5e7eb;text-align:right;"><strong>{int(r.get('filas_insertadas') or 0):,}</strong></td>
                    </tr>
                """)
            resolved_section_html = f"""
                <h3 style="color:#15803d;margin-top:20px;margin-bottom:8px;">Reportes Procesados en esta Corrida ({len(resolved_items)})</h3>
                <table style="border-collapse:collapse;width:100%;font-size:13px;">
                  <thead>
                    <tr style="background:#f0fdf4;text-align:left;">
                      <th style="padding:7px;border:1px solid #e5e7eb;">Fecha</th>
                      <th style="padding:7px;border:1px solid #e5e7eb;">Robot</th>
                      <th style="padding:7px;border:1px solid #e5e7eb;">Sede</th>
                      <th style="padding:7px;border:1px solid #e5e7eb;">Reporte</th>
                      <th style="padding:7px;border:1px solid #e5e7eb;">Estado</th>
                      <th style="padding:7px;border:1px solid #e5e7eb;text-align:right;">Filas Cargadas</th>
                    </tr>
                  </thead>
                  <tbody>{''.join(ok_rows)}</tbody>
                </table>
            """
        else:
            resolved_section_html = """
                <p style="margin-top:16px;color:#4b5563;">
                  No fue necesario descargar archivos nuevos porque toda la ventana ya estaba sincronizada previamente.
                </p>
            """

        html_body = f"""
        <html>
          <body style="font-family:Arial,sans-serif;color:#1f2937;line-height:1.5;">
            <h2 style="color:{header_color};margin-bottom:4px;">Informe de Sincronización ETL Parking</h2>
            <p style="margin-top:0;color:#4b5563;font-size:13px;">
              <strong>Fecha/Hora:</strong> {now_str} &nbsp;|&nbsp;
              <strong>Ventana:</strong> {html.escape(window_start)} &rarr; {html.escape(window_end)} &nbsp;|&nbsp;
              <strong>Duración:</strong> {duration_seconds:.1f}s
            </p>
            <div style="background:#f9fafb;border-left:4px solid {header_color};padding:10px 14px;margin:12px 0;font-size:14px;">
              <strong>{html.escape(status_banner)}</strong>
            </div>
            <table style="border-collapse:collapse;width:100%;font-size:13px;margin-bottom:12px;">
              <tr style="background:#f3f4f6;">
                <td style="padding:8px;border:1px solid #e5e7eb;"><strong>Esperados en ventana:</strong> {total_expected}</td>
                <td style="padding:8px;border:1px solid #e5e7eb;"><strong>Ya al día (omitidos):</strong> {already_ok_count}</td>
                <td style="padding:8px;border:1px solid #e5e7eb;"><strong>Procesados ahora:</strong> {len(resolved_items)} ({total_rows_inserted:,} filas)</td>
                <td style="padding:8px;border:1px solid #e5e7eb;"><strong>Pendientes / Error:</strong> {len(unresolved_items)}</td>
              </tr>
            </table>
            {failures_section_html}
            {resolved_section_html}
          </body>
        </html>
        """

        return SMTPNotifier._dispatch_email(subject, "\n".join(plain_lines), html_body)

    @staticmethod
    def send_failure_alert(
        failures: list[dict[str, str]],
        context_title: str = "Reintento Manual",
    ) -> bool:
        """Envía alerta puntual desde retry-errors cuando persisten fallos."""
        if not failures:
            return False
        today_str = datetime.now().date().isoformat()
        return SMTPNotifier.send_execution_report(
            window_start=today_str,
            window_end=today_str,
            total_expected=len(failures),
            already_ok_count=0,
            resolved_items=[],
            unresolved_items=failures,
            duration_seconds=0.0,
        )