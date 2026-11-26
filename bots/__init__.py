from bots.amano_japon_bot import AmanoJaponBot
from bots.amano_europa_bot import AmanoEuropaBot

BOT_REGISTRY = {
    "xoffice":  AmanoEuropaBot,
    "amano_japon": AmanoJaponBot,
}