"""BTF – Connecteur Exchange (CCXT)"""
import ccxt.async_support as ccxt
from cryptography.fernet import Fernet
import os

_fernet = Fernet(os.getenv("ENCRYPTION_KEY", Fernet.generate_key()))

class ExchangeConnector:
    def __init__(self, api_key_model):
        self.model = api_key_model
        raw_key    = _fernet.decrypt(api_key_model.encrypted_api_key.encode()).decode()
        raw_secret = _fernet.decrypt(api_key_model.encrypted_api_secret.encode()).decode()
        raw_pp     = _fernet.decrypt(api_key_model.encrypted_passphrase.encode()).decode() if api_key_model.encrypted_passphrase else None
        exchange_cls = getattr(ccxt, api_key_model.exchange, None)
        if not exchange_cls:
            raise ValueError(f"Exchange non supporté: {api_key_model.exchange}")
        config = {"apiKey": raw_key, "secret": raw_secret, "enableRateLimit": True}
        if raw_pp: config["password"] = raw_pp
        self.exchange = exchange_cls(config)

    async def place_order(self, order_data) -> dict:
        sym  = order_data.symbol
        side = order_data.side
        qty  = float(order_data.quantity)
        price= float(order_data.price) if order_data.price else None
        if order_data.order_type == "market":
            result = await self.exchange.create_market_order(sym, side, qty)
        else:
            result = await self.exchange.create_limit_order(sym, side, qty, price)
        return result

    async def cancel_order(self, symbol: str, order_id: str) -> dict:
        return await self.exchange.cancel_order(order_id, symbol)

    async def fetch_balance(self) -> dict:
        return await self.exchange.fetch_balance()

    async def close(self):
        await self.exchange.close()
