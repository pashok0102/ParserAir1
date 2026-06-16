import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str = "https://api.travelpayouts.com"
    currency: str = "rub"



def load_settings() -> Settings:
    api_key = os.getenv("AVIASALES_API_KEY") or os.getenv("TRAVELPAYOUTS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Не найден API ключ. Укажите AVIASALES_API_KEY в .env или переменных окружения."
        )

    return Settings(api_key=api_key.strip())
