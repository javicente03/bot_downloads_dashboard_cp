from core.base_bot import BaseBot
from bots.demo_bot import DemoBot
from bots.xoffice_bot import XOfficeBot

BOT_REGISTRY: dict[str, type[BaseBot]] = {
    DemoBot.name: DemoBot,
    XOfficeBot.name: XOfficeBot,
}