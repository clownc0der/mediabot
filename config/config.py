from dataclasses import dataclass
from environs import Env

@dataclass
class BotConfig:
    token: str
    admin_ids: list[int]

@dataclass
class Config:
    bot: BotConfig

def load_config() -> Config:
    env = Env()
    env.read_env()

    # Делаем ADMIN_IDS опциональным с значением по умолчанию
    admin_ids_str = env.str('ADMIN_IDS', default='1019678148')  # Ваш ID по умолчанию
    admin_ids = [int(id_str) for id_str in admin_ids_str.split(',')]

    return Config(
        bot=BotConfig(
            token=env.str('BOT_TOKEN'),
            admin_ids=admin_ids
        )
    ) 