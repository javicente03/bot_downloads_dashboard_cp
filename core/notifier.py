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
    def send_failure_alert(
        failures: list[dict[str, str]],
        context_title: str = "Ejecución Diaria / Auto-Sync",
    ) -> bool:
        """Envía un único correo consolidado con los ítems que quedaron pendientes/en error."""
        if not failures:
            return False

        if not settings.SMTP_ENABLED:
            log.info("SMTP_ENABLED=false. Se omite el envío de correo de alerta.")
            return False

        recipients = settings.smtp_recipients
        if not settings.SMTP_HOST or not recipients:
            log.warning("SMTP_HOST o SMTP_TO no configurados en .env. No se envió correo.")
            return False

        enriched: list[dict[str, str | bool]] = []
        for item in failures:
            is_ext, category = classify_error(item.get("mensaje_error"))
            enriched.append({**item, "is_external": is_ext, "categoria": category})

        if settings.SMTP_ONLY_EXTERNAL:
            enriched = [e for e in enriched if e["is_external"]]
            if not enriched:
                log.info("Los errores detectados son internos y SMTP_ONLY_EXTERNAL=true. No se envía correo.")
                return False

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        external_count = sum(1 for e in enriched if e["is_external"])
        subject = (
            f"[ALERTA ETL PARKING] {len(enriched)} pendiente(s) tras {context_title} "
            f"({external_count} externo(s))"
        )

        # Cuerpo en texto plano (fallback)
        plain_lines = [
            f"Alerta de Orquestador ETL Parking - {now_str}",
            f"Contexto: {context_title}",
            f"Total ítems sin completar: {len(enriched)} (Externos: {external_count})",
            "",
            "Detalle:",
        ]
        for e in enriched:
            plain_lines.append(
                f"- [{e['fecha_reporte']}] {e['bot_name']} | sede={e['sede']} | "
                f"reporte={e['reporte']} | {e['categoria']} -> {e.get('mensaje_error') or 'Sin ejecutar'}"
            )
        plain_lines.extend([
            "",
            "Nota: En la próxima ejecución diaria de 'python main.py auto-sync' estos días "
            "se reintentarán automáticamente mientras estén dentro de la ventana de búsqueda.",
            "Para forzar reintento manual ahora:",
            "  python main.py auto-sync --lookback-days 7",
        ])

        # Cuerpo HTML estructurado
        rows_html = []
        for e in enriched:
            badge_bg = "#fde8e8" if e["is_external"] else "#fef3c7"
            badge_fg = "#9b1c1c" if e["is_external"] else "#92400e"
            err_text = html.escape((e.get("mensaje_error") or "Pendiente sin registro")[:280])
            rows_html.append(f"""
                <tr>
                    <td style="padding:8px;border:1px solid #e5e7eb;white-space:nowrap;"><strong>{html.escape(str(e['fecha_reporte']))}</strong></td>
                    <td style="padding:8px;border:1px solid #e5e7eb;">{html.escape(str(e['bot_name']))}</td>
                    <td style="padding:8px;border:1px solid #e5e7eb;">{html.escape(str(e['sede']))}</td>
                    <td style="padding:8px;border:1px solid #e5e7eb;">{html.escape(str(e['reporte']))}</td>
                    <td style="padding:8px;border:1px solid #e5e7eb;">
                        <span style="background:{badge_bg};color:{badge_fg};padding:2px 6px;border-radius:4px;font-size:12px;font-weight:bold;">
                            {html.escape(str(e['categoria']))}
                        </span>
                    </td>
                    <td style="padding:8px;border:1px solid #e5e7eb;font-family:monospace;font-size:12px;">{err_text}</td>
                </tr>
            """)

        html_body = f"""
        <html>
          <body style="font-family:Arial,sans-serif;color:#1f2937;line-height:1.5;">
            <h2 style="color:#b91c1c;margin-bottom:4px;">Alerta de Sincronización ETL Parking</h2>
            <p style="margin-top:0;color:#4b5563;">
              <strong>Fecha/Hora:</strong> {now_str} &nbsp;|&nbsp;
              <strong>Proceso:</strong> {html.escape(context_title)} &nbsp;|&nbsp;
              <strong>Pendientes:</strong> {len(enriched)}
            </p>
            <p>
              Los siguientes reportes no pudieron completarse (por caída de portal, timeout de red o error de proceso).
              El robot los <strong>reintentará automáticamente</strong> en la próxima ejecución diaria:
            </p>
            <table style="border-collapse:collapse;width:100%;font-size:13px;">
              <thead>
                <tr style="background:#f3f4f6;text-align:left;">
                  <th style="padding:8px;border:1px solid #e5e7eb;">Fecha Reporte</th>
                  <th style="padding:8px;border:1px solid #e5e7eb;">Robot</th>
                  <th style="padding:8px;border:1px solid #e5e7eb;">Sede</th>
                  <th style="padding:8px;border:1px solid #e5e7eb;">Reporte</th>
                  <th style="padding:8px;border:1px solid #e5e7eb;">Tipo Fallo</th>
                  <th style="padding:8px;border:1px solid #e5e7eb;">Detalle</th>
                </tr>
              </thead>
              <tbody>
                {''.join(rows_html)}
              </tbody>
            </table>
            <p style="margin-top:16px;font-size:12px;color:#6b7280;">
              Comando manual de recuperación: <code>python main.py auto-sync --lookback-days {settings.AUTO_RETRY_LOOKBACK_DAYS}</code>
            </p>
          </body>
        </html>
        """

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
        msg["To"] = ", ".join(recipients)
        msg.set_content("\n".join(plain_lines))
        msg.add_alternative(html_body, subtype="html")

        try:
            log.info(f"Enviando correo de alerta SMTP a {', '.join(recipients)}...")
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

            log.success("Correo de alerta enviado correctamente.")
            return True
        except Exception as exc:
            log.error(f"No se pudo enviar el correo de alerta SMTP: {exc}")
            return False