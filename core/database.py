import math
import time
import polars as pl
import pyodbc
from sqlalchemy import create_engine, text
from sqlalchemy.exc import InterfaceError, OperationalError
from config.settings import settings
from core.logger import get_logger

log = get_logger("DATABASE")

engine = create_engine(
    settings.sqlserver_url,
    pool_pre_ping=True,
    pool_recycle=90,
    connect_args={"timeout": 30},
)

TRANSIENT_SQL_ERRORS = (
    "08S01",
    "08S03",
    "08001",
    "HYT00",
    "HYT01",
    "Communication link failure",
    "Login timeout expired",
    "wait operation timed out",
)


class SQLServerManager:
    @staticmethod
    def _prepare_records(df: pl.DataFrame) -> list[dict]:
        dt_exprs = [
            pl.col(c).dt.truncate("1s").alias(c)
            for c, dtype in zip(df.columns, df.dtypes)
            if isinstance(dtype, pl.Datetime)
        ]
        if dt_exprs:
            df = df.with_columns(dt_exprs)

        records = df.to_dicts()
        for row in records:
            for k, v in row.items():
                if isinstance(v, float) and math.isnan(v):
                    row[k] = None
        return records

    @staticmethod
    def _bulk_insert(connection, df: pl.DataFrame, table_name: str, schema: str) -> int:
        cols = df.columns
        num_cols = len(cols)
        batch_size = max(1, min(45, 2000 // num_cols))

        cols_sql = ", ".join(f"[{c}]" for c in cols)
        records = SQLServerManager._prepare_records(df)
        total_rows = len(records)

        for start in range(0, total_rows, batch_size):
            batch = records[start : start + batch_size]
            values_clauses = []
            bind_params: dict = {}

            for idx, row in enumerate(batch):
                row_placeholders = []
                for col in cols:
                    param_key = f"{col}_{idx}"
                    row_placeholders.append(f":{param_key}")
                    bind_params[param_key] = row[col]
                values_clauses.append(f"({', '.join(row_placeholders)})")

            insert_sql = text(
                f"INSERT INTO [{schema}].[{table_name}] ({cols_sql}) "
                f"VALUES {', '.join(values_clauses)}"
            )
            connection.execute(insert_sql, bind_params)
            time.sleep(0.015)

        return total_rows

    @staticmethod
    def _run_with_retry(operation, max_retries: int = 5):
        backoff_seconds = [4, 8, 15, 25, 30]
        for attempt in range(1, max_retries + 1):
            try:
                with engine.begin() as connection:
                    return operation(connection)
            except InterfaceError as exc:
                if "IM002" in str(exc):
                    log.error(
                        f"Driver ODBC no encontrado. Disponibles en Windows: {pyodbc.drivers()}."
                    )
                raise
            except OperationalError as exc:
                err_msg = str(exc)
                is_transient = any(code in err_msg for code in TRANSIENT_SQL_ERRORS)
                if is_transient and attempt < max_retries:
                    wait_s = backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)]
                    log.warning(
                        f"Túnel VPN/SQL Server inestable (intento {attempt}/{max_retries}). "
                        f"Esperando {wait_s}s para reconectar..."
                    )
                    engine.dispose()
                    time.sleep(wait_s)
                    continue
                raise

    @staticmethod
    def check_connection() -> None:
        """Despierta el túnel VPN y verifica conectividad con SQL Server antes de operar."""
        log.info(f"Verificando conexión a SQL Server ({settings.DB_HOST}:{settings.DB_PORT})...")
        SQLServerManager._run_with_retry(lambda conn: conn.execute(text("SELECT 1")))
        log.info("Conexión a SQL Server establecida.")

    @staticmethod
    def insert_dataframe(
        df: pl.DataFrame,
        table_name: str,
        schema: str = "dbo",
    ) -> int:
        if df.is_empty():
            log.warning(f"DataFrame vacío. No se insertaron filas en [{schema}].[{table_name}].")
            return 0

        log.info(f"Insertando {df.height} filas en [{schema}].[{table_name}]...")

        def _op(connection):
            return SQLServerManager._bulk_insert(connection, df, table_name, schema)

        total_rows = SQLServerManager._run_with_retry(_op)
        log.success(f"Carga completada: {total_rows} registros en [{schema}].[{table_name}].")
        return total_rows

    @staticmethod
    def replace_by_sede_and_dates(
        df: pl.DataFrame,
        table_name: str,
        sede: str,
        date_column: str,
        schema: str = "dbo",
    ) -> int:
        """Elimina registros previos de la sede para las fechas del lote e inserta los nuevos."""
        if df.is_empty():
            log.warning(f"[{sede.upper()}] Sin registros para insertar en [{schema}].[{table_name}].")
            return 0

        if df[date_column].dtype == pl.Null or df[date_column].drop_nulls().is_empty():
            log.error(
                f"[{sede.upper()}] La columna '{date_column}' no contiene fechas válidas en [{table_name}]."
            )
            return 0

        dates_series = df.select(pl.col(date_column).dt.date().drop_nulls().unique()).to_series()
        unique_dates = [d.isoformat() for d in dates_series.to_list()]

        def _op(connection):
            for date_str in unique_dates:
                delete_sql = text(
                    f"DELETE FROM [{schema}].[{table_name}] "
                    f"WHERE sede = :sede AND CAST([{date_column}] AS DATE) = :fecha"
                )
                result = connection.execute(delete_sql, {"sede": sede, "fecha": date_str})
                if result.rowcount:
                    log.info(
                        f"[{sede.upper()}] Limpiados {result.rowcount} registros previos "
                        f"en [{table_name}] para fecha {date_str}."
                    )
            return SQLServerManager._bulk_insert(connection, df, table_name, schema)

        total_rows = SQLServerManager._run_with_retry(_op)
        log.success(
            f"[{sede.upper()}] {total_rows} filas cargadas en [{schema}].[{table_name}] "
            f"(fechas: {', '.join(unique_dates)})."
        )
        return total_rows

    @staticmethod
    def execute_query(query: str, params: dict | None = None):
        return SQLServerManager._run_with_retry(
            lambda connection: connection.execute(text(query), params or {})
        )

    @staticmethod
    def log_execution(
        bot_name: str,
        sede: str,
        reporte: str,
        fecha_reporte: str,
        filas_insertadas: int,
        estado: str,
        mensaje_error: str | None = None,
    ) -> None:
        """Registra el resultado de cada sede/reporte para monitoreo en el dashboard."""
        sql = """
            INSERT INTO [dbo].[bot_ejecuciones]
                (bot_name, sede, reporte, fecha_reporte, filas_insertadas, estado, mensaje_error)
            VALUES
                (:bot_name, :sede, :reporte, :fecha_reporte, :filas_insertadas, :estado, :mensaje_error)
        """
        params = {
            "bot_name": bot_name[:50],
            "sede": sede[:30],
            "reporte": reporte[:50],
            "fecha_reporte": fecha_reporte,
            "filas_insertadas": filas_insertadas,
            "estado": estado[:20],
            "mensaje_error": mensaje_error[:500] if mensaje_error else None,
        }
        try:
            SQLServerManager.execute_query(sql, params)
        except Exception as exc:
            log.warning(f"No se pudo registrar auditoría en bot_ejecuciones ({sede}/{reporte}): {exc}")

    @classmethod
    def get_latest_executions(
        cls,
        bot_name: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        """Devuelve el estado más reciente de cada combinación (bot_name, sede, reporte, fecha_reporte)."""
        from sqlalchemy import text

        conditions = ["1 = 1"]
        params: dict[str, object] = {}

        if bot_name and bot_name != "todos":
            conditions.append("bot_name = :bot_name")
            params["bot_name"] = bot_name
        if start_date:
            conditions.append("fecha_reporte >= :start_date")
            params["start_date"] = start_date
        if end_date:
            conditions.append("fecha_reporte <= :end_date")
            params["end_date"] = end_date

        where_sql = " AND ".join(conditions)
        query = text(f"""
            WITH RankedExecutions AS (
                SELECT
                    id,
                    bot_name,
                    sede,
                    reporte,
                    CONVERT(varchar(10), fecha_reporte, 23) AS fecha_reporte,
                    filas_insertadas,
                    estado,
                    mensaje_error,
                    ROW_NUMBER() OVER (
                        PARTITION BY bot_name, sede, reporte, fecha_reporte
                        ORDER BY id DESC
                    ) AS rn
                FROM dbo.bot_ejecuciones
                WHERE {where_sql}
            )
            SELECT
                bot_name,
                sede,
                reporte,
                fecha_reporte,
                filas_insertadas,
                estado,
                mensaje_error
            FROM RankedExecutions
            WHERE rn = 1
            ORDER BY fecha_reporte ASC, bot_name ASC, sede ASC, reporte ASC
        """)

        engine_getter = getattr(cls, "_get_engine", None)
        engine = (
            engine_getter()
            if callable(engine_getter)
            else (getattr(cls, "_engine", None) or getattr(cls, "engine", None))
        )
        if engine is None:
            raise RuntimeError("No se encontró una instancia de engine activa en SQLServerManager.")

        with engine.connect() as conn:
            rows = conn.execute(query, params).mappings().all()
            return [dict(r) for r in rows]