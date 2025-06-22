"""
Компонент для получения информации о позициях от Hyperliquid
Реализует интерфейс IPositionProvider
"""

import time
from typing import Dict, List
from hyperliquid.info import Info
from hyperliquid.utils.constants import MAINNET_API_URL
from logger_config import setup_unified_logger
from interfaces import IPositionProvider, PositionInfo


class HyperliquidPositionProvider(IPositionProvider):
    """Провайдер позиций для Hyperliquid"""

    def __init__(self, account_address: str):
        self.logger = setup_unified_logger("position_provider")
        self.info = Info(MAINNET_API_URL, skip_ws=True)
        self.account_address = account_address
        self._position_cache = {}
        self._cache_timestamp = 0
        self._cache_ttl = 5  # Кэш на 5 секунд для позиций

        self.logger.info("[INIT] Position provider initialized")

    def _is_cache_valid(self) -> bool:
        """Проверка валидности кэша"""
        return time.time() - self._cache_timestamp < self._cache_ttl

    def get_positions(self) -> Dict[str, float]:
        """Получение текущих позиций с кэшированием"""
        operation_start = time.time()

        try:
            # Проверяем кэш
            if self._is_cache_valid() and self._position_cache:
                self.logger.debug("[CACHE] Positions cache hit")
                return self._position_cache.copy()

            user_state = self.info.user_state(self.account_address)
            asset_positions = user_state.get('assetPositions', [])
            positions = {}

            for pos in asset_positions:
                item = pos.get('position', {})
                coin = item.get('coin')
                sz = item.get('szi', 0.0)
                if coin:
                    positions[coin] = float(sz)

            # Обновляем кэш
            self._position_cache = positions
            self._cache_timestamp = time.time()

            duration = time.time() - operation_start
            self.logger.debug(f"[PERF] Get positions completed in {duration:.3f}s")

            # Логируем открытые позиции
            open_positions = {k: v for k, v in positions.items() if abs(v) > 1e-8}
            if open_positions:
                self.logger.debug(f"[POSITIONS] Open: {open_positions}")

            return positions

        except Exception as e:
            self.logger.error(f"[ERROR] Failed to get positions: {e}")
            return {}

    def get_position_details(self) -> List[PositionInfo]:
        """Получение детальной информации о позициях"""
        operation_start = time.time()

        try:
            user_state = self.info.user_state(self.account_address)
            asset_positions = user_state.get('assetPositions', [])
            position_details = []

            for pos in asset_positions:
                position_info = pos.get('position', {})
                coin = position_info.get('coin')

                if coin:
                    size = float(position_info.get('szi', 0.0))
                    unrealized_pnl = float(position_info.get('unrealizedPnl', 0.0))
                    margin_used = float(position_info.get('marginUsed', 0.0))

                    # Получаем leverage
                    leverage_info = position_info.get('leverage')
                    if leverage_info and isinstance(leverage_info, dict):
                        leverage = float(leverage_info.get('value', 1.0))
                    elif leverage_info:
                        leverage = float(leverage_info)
                    else:
                        leverage = 1.0

                    if abs(size) > 1e-8:  # Только открытые позиции
                        position_details.append(PositionInfo(
                            symbol=coin,
                            size=size,
                            unrealized_pnl=unrealized_pnl,
                            margin_used=margin_used,
                            leverage=leverage
                        ))

            duration = time.time() - operation_start
            self.logger.debug(f"[PERF] Get position details completed in {duration:.3f}s")

            return position_details

        except Exception as e:
            self.logger.error(f"[ERROR] Failed to get position details: {e}")
            return []

    def get_account_summary(self) -> Dict[str, float]:
        """Получение сводки по аккаунту"""
        operation_start = time.time()

        try:
            user_state = self.info.user_state(self.account_address)
            margin_summary = user_state.get('marginSummary', {})

            summary = {
                'account_value': float(margin_summary.get('accountValue', 0.0)),
                'total_margin_used': float(margin_summary.get('totalMarginUsed', 0.0)),
                'total_raw_usd': float(margin_summary.get('totalRawUsd', 0.0)),
                'withdrawable': float(margin_summary.get('withdrawable', 0.0))
            }

            duration = time.time() - operation_start
            self.logger.debug(f"[PERF] Get account summary completed in {duration:.3f}s")
            self.logger.debug(
                f"[ACCOUNT] NAV: ${summary['account_value']:.2f}, Margin: ${summary['total_margin_used']:.2f}")

            return summary

        except Exception as e:
            self.logger.error(f"[ERROR] Failed to get account summary: {e}")
            return {}

    def invalidate_cache(self) -> None:
        """Принудительная очистка кэша"""
        self._position_cache.clear()
        self._cache_timestamp = 0
        self.logger.debug("[CACHE] Position cache invalidated")
