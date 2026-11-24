from core.base_bot import BaseBot
from bots.demo_bot import DemoBot

BOT_REGISTRY: dict[str, type[BaseBot]] = {
    DemoBot.name: DemoBot,
}