from pathlib import Path
import pyodbc
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

BASE_DIR = Path(__file__).resolve().parent.parent

PREFERRED_SQLSERVER_DRIVERS = [
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
    "ODBC Driver 13 for SQL Server",
    "SQL Server Native Client 11.0",
    "SQL Server",
]


def detect_sqlserver_driver(configured_driver: str) -> str:
    installed = pyodbc.drivers()
    if configured_driver in installed:
        return configured_driver
    for candidate in PREFERRED_SQLSERVER_DRIVERS:
        if candidate in installed:
            return candidate
    return configured_driver


class Settings(BaseSettings):
    DB_HOST: str
    DB_PORT: int = 1433
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    DB_DRIVER: str = "ODBC Driver 18 for SQL Server"

    HEADLESS: bool = True
    DOWNLOAD_TIMEOUT_MS: int = 60000

    # Credenciales XOffice
    XOFFICE_PICHIMAPU_USER: str = ""
    XOFFICE_PICHIMAPU_PASS: str = ""
    XOFFICE_INDISA_USER: str = ""
    XOFFICE_INDISA_PASS: str = ""
    XOFFICE_RECOLETA_USER: str = ""
    XOFFICE_RECOLETA_PASS: str = ""

    DOWNLOADS_DIR: Path = BASE_DIR / "downloads"
    LOGS_DIR: Path = BASE_DIR / "logs"

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def resolved_db_driver(self) -> str:
        return detect_sqlserver_driver(self.DB_DRIVER)

    @property
    def sqlserver_url(self) -> URL:
        driver = self.resolved_db_driver
        query_params: dict[str, str] = {"driver": driver}
        # El driver legacy "SQL Server" no soporta TrustServerCertificate
        if "ODBC Driver" in driver or "Native Client" in driver:
            query_params["TrustServerCertificate"] = "yes"

        return URL.create(
            drivername="mssql+pyodbc",
            username=self.DB_USER,
            password=self.DB_PASSWORD,
            host=self.DB_HOST,
            port=self.DB_PORT,
            database=self.DB_NAME,
            query=query_params,
        )

    @property
    def xoffice_sites(self) -> dict[str, dict[str, str]]:
        return {
            "pichimapu": {
                "nombre": "Pichimapu Talca",
                "base_url": "https://192.168.34.100",
                "user": self.XOFFICE_PICHIMAPU_USER,
                "password": self.XOFFICE_PICHIMAPU_PASS,
            },
            "indisa": {
                "nombre": "Clinica Indisa",
                "base_url": "https://172.16.85.40",
                "user": self.XOFFICE_INDISA_USER,
                "password": self.XOFFICE_INDISA_PASS,
            },
            "recoleta": {
                "nombre": "Nucleo Recoleta",
                "base_url": "https://20.20.20.100",
                "user": self.XOFFICE_RECOLETA_USER,
                "password": self.XOFFICE_RECOLETA_PASS,
            },
        }


settings = Settings()