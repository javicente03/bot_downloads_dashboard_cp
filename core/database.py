import polars as pl
from sqlalchemy import create_engine, event, text
from config.settings import settings
from core.logger import get_logger

log = get_logger("DATABASE")

engine = create_engine(
    settings.sqlserver_url,
    pool_pre_ping=True,
    fast_executemany=True,  # Acelera inserciones masivas en SQL Server
)

@event.listens_for(engine, "before_cursor_execute")
def receive_before_cursor_execute(conn, cursor, statement, params, context, executemany):
    if executemany:
        cursor.fast_executemany = True


class SQLServerManager:
    @staticmethod
    def insert_dataframe(
        df: pl.DataFrame,
        table_name: str,
        schema: str = "dbo",
        if_exists: str = "append",
        chunk_size: int = 5000,
    ) -> int:
        if df.is_empty():
            log.warning(f"DataFrame vacío. No se insertaron filas en {schema}.{table_name}.")
            return 0

        total_rows = df.height
        log.info(f"Insertando {total_rows} filas en [{schema}].[{table_name}]...")

        # Convertimos a pandas solo para el puente con SQLAlchemy to_sql
        pdf = df.to_pandas()
        with engine.begin() as connection:
            pdf.to_sql(
                name=table_name,
                con=connection,
                schema=schema,
                if_exists=if_exists,
                index=False,
                chunksize=chunk_size,
            )

        log.success(f"Carga completada: {total_rows} registros en [{schema}].[{table_name}].")
        return total_rows

    @staticmethod
    def execute_query(query: str, params: dict | None = None):
        with engine.begin() as connection:
            return connection.execute(text(query), params or {})