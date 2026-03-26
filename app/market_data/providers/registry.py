from __future__ import annotations

from app.config import Settings
from app.market_data.providers.akshare import AkShareAdapter
from app.market_data.fallback.chain import ProviderChain
from app.market_data.providers.china_fast import ChinaFastAdapter
from app.market_data.providers.mock_provider import MockMarketDataAdapter


class MarketDataProviderRegistry:
    def __init__(self, settings: Settings) -> None:
        self.provider_map = {
            "mock": MockMarketDataAdapter(),
            "chinafast": ChinaFastAdapter(),
            "akshare": AkShareAdapter(),
        }
        self.quote_chain = ProviderChain(
            self._ordered_chain(settings.market_primary_quote_provider, settings, ("get_quote", "get_indices", "healthcheck"))
        )
        self.fundamentals_chain = ProviderChain(
            self._ordered_chain(settings.market_primary_fundamentals_provider, settings, ("get_security_profile",))
        )
        self.fund_chain = ProviderChain(self._ordered_chain(settings.market_primary_fund_provider, settings, ("get_fund", "get_hot_funds")))
        self.news_chain = ProviderChain(self._ordered_chain(settings.market_primary_news_provider, settings, ("get_news",)))
        self.technical_chain = ProviderChain(
            self._ordered_chain(settings.market_primary_technical_provider, settings, ("get_technical_snapshot",))
        )
        self.screener_chain = ProviderChain(
            self._ordered_chain(settings.market_primary_screener_provider, settings, ("screen_stocks", "screen_funds", "get_hot_sectors"))
        )

    def _ordered_chain(self, primary: str, settings: Settings, required_methods: tuple[str, ...]) -> list[object]:
        ordered_names: list[str] = []
        for name in (primary, *settings.market_fallback_order, "akshare", "mock"):
            if name in self.provider_map and name not in ordered_names:
                provider = self.provider_map[name]
                if all(hasattr(provider, method) for method in required_methods):
                    ordered_names.append(name)
        return [self.provider_map[name] for name in ordered_names]

    def all_providers(self) -> list[object]:
        return list(self.provider_map.values())
