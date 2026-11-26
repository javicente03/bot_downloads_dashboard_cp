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

    # Credenciales Amano Europa (XOffice)
    XOFFICE_PICHIMAPU_USER: str = ""
    XOFFICE_PICHIMAPU_PASS: str = ""
    XOFFICE_INDISA_USER: str = ""
    XOFFICE_INDISA_PASS: str = ""
    XOFFICE_RECOLETA_USER: str = ""
    XOFFICE_RECOLETA_PASS: str = ""

    # Credenciales Amano Japón (ExACT)
    AMANO_JP_PLD_USER: str = ""
    AMANO_JP_PLD_PASS: str = ""
    AMANO_JP_QUILLOTA_USER: str = ""
    AMANO_JP_QUILLOTA_PASS: str = ""
    AMANO_JP_HOMECENTER_USER: str = ""
    AMANO_JP_HOMECENTER_PASS: str = ""
    AMANO_JP_PLAZUELA_USER: str = ""
    AMANO_JP_PLAZUELA_PASS: str = ""
    AMANO_JP_CONQUISTADORES_USER: str = ""
    AMANO_JP_CONQUISTADORES_PASS: str = ""

    # Credenciales RedComercio CPS (ParkingApp)
    REDCOMERCIO_CPS_USER: str = ""
    REDCOMERCIO_CPS_PASS: str = ""

    # Credenciales RedComercio Dávila (ParkingApp)
    REDCOMERCIO_DAVILA_USER: str = ""
    REDCOMERCIO_DAVILA_PASS: str = ""

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
    def amano_europa_sites(self) -> dict[str, dict[str, str]]:
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

    @property
    def amano_japon_sites(self) -> dict[str, dict[str, str]]:
        return {
            "pld": {
                "nombre": "PLD",
                "login_url": "http://192.168.195.166/ExACT/menu/login/login.aspx",
                "user": self.AMANO_JP_PLD_USER,
                "password": self.AMANO_JP_PLD_PASS,
            },
            "quillota": {
                "nombre": "Quillota",
                "login_url": "http://192.168.195.119/ExACT/menu/login/login.aspx",
                "user": self.AMANO_JP_QUILLOTA_USER,
                "password": self.AMANO_JP_QUILLOTA_PASS,
            },
            "homecenter": {
                "nombre": "Homecenter",
                "login_url": "http://192.168.0.100/ExACT/menu/login/login.aspx",
                "user": self.AMANO_JP_HOMECENTER_USER,
                "password": self.AMANO_JP_HOMECENTER_PASS,
            },
            "plazuela": {
                "nombre": "Plazuela",
                "login_url": "http://26.140.110.60/ExACT/menu/login/login.aspx",
                "user": self.AMANO_JP_PLAZUELA_USER,
                "password": self.AMANO_JP_PLAZUELA_PASS,
            },
            "conquistadores": {
                "nombre": "Ind. Los Conquistadores",
                "login_url": "http://26.59.65.213/ExACT/menu/login/login.aspx",
                "user": self.AMANO_JP_CONQUISTADORES_USER,
                "password": self.AMANO_JP_CONQUISTADORES_PASS,
            },
        }

    @property
    def redcomercio_cps_config(self) -> dict[str, str]:
        return {
            "nombre": "RedComercio CPS",
            "base_url": "https://admin.parkingapp.cl",
            "login_url": "https://admin.parkingapp.cl/ingresar",
            "user": self.REDCOMERCIO_CPS_USER,
            "password": self.REDCOMERCIO_CPS_PASS,
        }

    @property
    def redcomercio_davila_config(self) -> dict[str, str]:
        return {
            "nombre": "RedComercio Dávila",
            "base_url": "https://admin.parkingapp.cl",
            "login_url": "https://admin.parkingapp.cl/ingresar",
            "user": self.REDCOMERCIO_DAVILA_USER,
            "password": self.REDCOMERCIO_DAVILA_PASS,
        }


settings = Settings()