from bots.amano_europa_bot import AmanoEuropaBot
from bots.amano_japon_bot import AmanoJaponBot
from bots.redcomercio_cps_bot import RedComercioCPSBot
from bots.redcomercio_davila_bot import RedComercioDavilaBot

BOT_REGISTRY = {
    "amano_europa": AmanoEuropaBot,
    "amano_japon": AmanoJaponBot,
    "redcomercio_cps": RedComercioCPSBot,
    "redcomercio_davila": RedComercioDavilaBot,
}