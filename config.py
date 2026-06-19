import os
from dotenv import load_dotenv
from pydantic import Field, validator
from pydantic_settings import BaseSettings

load_dotenv()  # loads .env if present

class Settings(BaseSettings):
    alpaca_api_key: str = Field(..., env='ALPACA_API_KEY')
    alpaca_api_secret: str = Field(..., env='ALPACA_API_SECRET')
    max_capital_allocation: float = Field(0.20, description='Maximum % of account equity to allocate')
    log_level: str = Field('INFO', env='LOG_LEVEL')

    @validator('log_level')
    def _validate_log_level(cls, v: str) -> str:
        allowed = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
        if v.upper() not in allowed:
            raise ValueError(f'log_level must be one of {allowed}')
        return v.upper()

settings = Settings()
