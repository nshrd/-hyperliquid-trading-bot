"""
Кастомные исключения для Hyperliquid Trading Bot
Заменяют generic Exception handling более специфичными типами
"""


class HyperliquidTradingError(Exception):
    """Базовое исключение для всех ошибок торгового бота"""
    pass


class ConfigurationError(HyperliquidTradingError):
    """Ошибки конфигурации"""
    pass


class APIError(HyperliquidTradingError):
    """Ошибки API Hyperliquid"""
    pass


class OrderExecutionError(APIError):
    """Ошибки выполнения ордеров"""
    pass


class LeverageUpdateError(APIError):
    """Ошибки обновления плеча"""
    pass


class PositionError(HyperliquidTradingError):
    """Ошибки работы с позициями"""
    pass


class MarketDataError(HyperliquidTradingError):
    """Ошибки получения рыночных данных"""
    pass


class RiskManagementError(HyperliquidTradingError):
    """Ошибки управления рисками"""
    pass


class StrategyError(HyperliquidTradingError):
    """Ошибки стратегии торговли"""
    pass


class ValidationError(HyperliquidTradingError):
    """Ошибки валидации данных"""
    pass


class NetworkError(APIError):
    """Ошибки сети/подключения"""
    pass


class InsufficientFundsError(OrderExecutionError):
    """Недостаточно средств для выполнения операции"""
    pass


class InvalidOrderSizeError(OrderExecutionError):
    """Некорректный размер ордера"""
    pass


class LeverageComplianceError(RiskManagementError):
    """Ошибки соответствия плеча требованиям"""
    pass


class PortfolioStateError(HyperliquidTradingError):
    """Ошибки состояния портфеля"""
    pass
