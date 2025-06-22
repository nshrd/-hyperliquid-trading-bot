"""
Модуль для работы с метаданными активов Hyperliquid
Заменяет legacy клиент для получения asset_meta
"""

import time
from typing import Dict, Any
from hyperliquid.info import Info
from hyperliquid.utils.constants import MAINNET_API_URL
from logger_config import setup_unified_logger


class AssetMetadataProvider:
    """Провайдер метаданных активов"""

    def __init__(self):
        self.logger = setup_unified_logger("asset_metadata")
        self.info = Info(MAINNET_API_URL, skip_ws=True)
        self._cache = {}
        self._cache_timestamp = 0
        self._cache_ttl = 300  # 5 минут

    def get_asset_meta(self, force_refresh: bool = False) -> Dict[str, dict]:
        """Получение метаданных активов с кэшированием"""
        current_time = time.time()

        # Проверяем кэш
        if not force_refresh and self._cache and (current_time - self._cache_timestamp) < self._cache_ttl:
            self.logger.debug("Using cached asset metadata")
            return self._cache

        try:
            self.logger.info("Fetching fresh asset metadata")

            # Получаем метаданные через API
            meta_response = self.info.meta()

            if not meta_response or 'universe' not in meta_response:
                self.logger.error("Invalid meta response structure")
                return self._cache if self._cache else {}

            # Обрабатываем данные
            asset_meta = {}
            universe = meta_response['universe']

            for asset_info in universe:
                name = asset_info.get('name')
                if name:
                    asset_meta[name] = {
                        'szDecimals': asset_info.get('szDecimals', 6),
                        'szStep': asset_info.get('szStep', '0.000001'),
                        'maxLeverage': asset_info.get('maxLeverage', 50),
                        'onlyIsolated': asset_info.get('onlyIsolated', False)
                    }

            # Обновляем кэш
            self._cache = asset_meta
            self._cache_timestamp = current_time

            self.logger.info(f"Asset metadata updated: {len(asset_meta)} assets")
            return asset_meta

        except Exception as e:
            self.logger.error(f"Failed to fetch asset metadata: {e}")
            return self._cache if self._cache else {}

    def get_asset_info(self, symbol: str) -> Dict[str, Any]:
        """Получение информации о конкретном активе"""
        meta = self.get_asset_meta()
        return meta.get(symbol, {})

    def get_size_decimals(self, symbol: str) -> int:
        """Получение количества десятичных знаков для размера позиции"""
        asset_info = self.get_asset_info(symbol)
        return asset_info.get('szDecimals', 6)

    def get_size_step(self, symbol: str) -> str:
        """Получение минимального шага размера позиции"""
        asset_info = self.get_asset_info(symbol)
        return asset_info.get('szStep', '0.000001')

    def get_max_leverage(self, symbol: str) -> int:
        """Получение максимального плеча для актива"""
        asset_info = self.get_asset_info(symbol)
        return asset_info.get('maxLeverage', 50)


# Глобальный экземпляр для использования в других модулях
_asset_metadata_provider = None


def get_asset_metadata_provider() -> AssetMetadataProvider:
    """Получение глобального экземпляра провайдера метаданных"""
    global _asset_metadata_provider
    if _asset_metadata_provider is None:
        _asset_metadata_provider = AssetMetadataProvider()
    return _asset_metadata_provider
