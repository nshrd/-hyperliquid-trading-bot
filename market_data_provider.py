"""
Компонент для получения рыночных данных от Hyperliquid
Реализует интерфейс IMarketDataProvider
"""

import time
from typing import Dict, List
from hyperliquid.info import Info
from hyperliquid.utils.constants import MAINNET_API_URL
from logger_config import setup_unified_logger
from interfaces import IMarketDataProvider
# from exceptions import MarketDataError, NetworkError  # TODO: Use when implementing error handling


class HyperliquidMarketDataProvider(IMarketDataProvider):
    """Провайдер рыночных данных для Hyperliquid"""

    def __init__(self):
        self.logger = setup_unified_logger("market_data")
        self.info = Info(MAINNET_API_URL, skip_ws=True)
        self._prices_cache = {}
        self._funding_cache = {}
        self._cache_timestamp = 0
        self._cache_ttl = 10  # Кэш на 10 секунд

        self.logger.info("[INIT] Market data provider initialized")

    def _is_cache_valid(self) -> bool:
        """Проверка валидности кэша"""
        return time.time() - self._cache_timestamp < self._cache_ttl

    def get_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Получение цен для списка символов с кэшированием"""
        operation_start = time.time()

        try:
            # Проверяем кэш
            if self._is_cache_valid() and self._prices_cache:
                cache_hit = all(symbol in self._prices_cache for symbol in symbols)
                if cache_hit:
                    self.logger.debug(f"[CACHE] Prices cache hit for {symbols}")
                    return {symbol: self._prices_cache[symbol] for symbol in symbols}

            # Получаем данные от API
            markets = self.info.all_mids()
            prices = {}

            for symbol in symbols:
                price_raw = markets.get(symbol, 'NOT FOUND')
                if price_raw in ('NOT FOUND', None, '', 0, 0.0):
                    self.logger.warning(f"[ERROR] Price for {symbol} not found or zero")
                    prices[symbol] = 0.0
                else:
                    prices[symbol] = float(price_raw)

            # Обновляем кэш
            self._prices_cache.update(prices)
            self._cache_timestamp = time.time()

            duration = time.time() - operation_start
            self.logger.debug(f"[PERF] Get prices completed in {duration:.3f}s for {len(symbols)} symbols")

            return prices

        except Exception as e:
            self.logger.error(f"[ERROR] Failed to get prices: {e}")
            return {symbol: 0.0 for symbol in symbols}

    def get_funding_rates(self, symbols: List[str]) -> Dict[str, float]:
        """Получение ставок фандинга с кэшированием"""
        operation_start = time.time()

        try:
            # Проверяем кэш
            if self._is_cache_valid() and self._funding_cache:
                cache_hit = all(symbol in self._funding_cache for symbol in symbols)
                if cache_hit:
                    self.logger.debug(f"[CACHE] Funding cache hit for {symbols}")
                    return {symbol: self._funding_cache[symbol] for symbol in symbols}

            funding = {}

            for symbol in symbols:
                try:
                    f_hist = self.info.funding_history(symbol, 0)
                    if f_hist and len(f_hist) > 0:
                        funding[symbol] = float(f_hist[-1].get('fundingRate', 0.0))
                        self.logger.debug(f"[FUNDING] {symbol}: {funding[symbol]:.6f}")
                    else:
                        funding[symbol] = 0.0
                        self.logger.warning(f"[FUNDING] No funding data for {symbol}")

                except Exception as e:
                    self.logger.error(f"[ERROR] Failed to get funding for {symbol}: {e}")
                    funding[symbol] = 0.0

            # Обновляем кэш
            self._funding_cache.update(funding)

            duration = time.time() - operation_start
            self.logger.debug(f"[PERF] Get funding rates completed in {duration:.3f}s for {len(symbols)} symbols")

            return funding

        except Exception as e:
            self.logger.error(f"[ERROR] Failed to get funding rates: {e}")
            return {symbol: 0.0 for symbol in symbols}

    def get_funding_history(self, symbol: str, start_time: int = 0) -> List[dict]:
        """Получение истории фандинга для символа"""
        operation_start = time.time()

        try:
            funding_records = self.info.funding_history(symbol, start_time)

            duration = time.time() - operation_start
            self.logger.debug(f"[PERF] Get funding history for {symbol} completed in {duration:.3f}s")
            self.logger.debug(f"[FUNDING] Retrieved {len(funding_records)} funding records for {symbol}")

            return funding_records

        except Exception as e:
            self.logger.error(f"[ERROR] Failed to get funding history for {symbol}: {e}")
            return []

    def invalidate_cache(self) -> None:
        """Принудительная очистка кэша"""
        self._prices_cache.clear()
        self._funding_cache.clear()
        self._cache_timestamp = 0
        self.logger.debug("[CACHE] Cache invalidated")
