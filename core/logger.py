import sys
from loguru import logger
from config.settings import settings

settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)

logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{extra[bot]}</cyan> - <level>{message}</level>",
    level="INFO",
)
logger.add(
    settings.LOGS_DIR / "scraper_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="30 days",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[bot]} - {message}",
    level="DEBUG",
)

def get_logger(bot_name: str = "SYSTEM"):
    return logger.bind(bot=bot_name)