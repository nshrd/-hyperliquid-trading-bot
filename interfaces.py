"""
Интерфейсы для компонентов торгового бота
Обеспечивает слабую связанность и тестируемость
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class OrderResult:
    """Результат размещения ордера"""
    success: bool
    order_id: Optional[str] = None
    filled_size: float = 0.0
    avg_price: float = 0.0
    commission: float = 0.0
    error_message: Optional[str] = None


@dataclass
class PositionInfo:
    """Информация о позиции"""
    symbol: str
    size: float
    unrealized_pnl: float
    margin_used: float
    leverage: float


class IMarketDataProvider(ABC):
    """Интерфейс для получения рыночных данных"""

    @abstractmethod
    def get_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Получение цен для списка символов"""
        pass

    @abstractmethod
    def get_funding_rates(self, symbols: List[str]) -> Dict[str, float]:
        """Получение ставок фандинга"""
        pass

    @abstractmethod
    def get_funding_history(self, symbol: str, start_time: int = 0) -> List[dict]:
        """Получение истории фандинга"""
        pass


class IPositionProvider(ABC):
    """Интерфейс для получения информации о позициях"""

    @abstractmethod
    def get_positions(self) -> Dict[str, float]:
        """Получение текущих позиций"""
        pass

    @abstractmethod
    def get_position_details(self) -> List[PositionInfo]:
        """Получение детальной информации о позициях"""
        pass

    @abstractmethod
    def get_account_summary(self) -> Dict[str, float]:
        """Получение сводки по аккаунту"""
        pass


class IOrderExecutor(ABC):
    """Интерфейс для исполнения ордеров"""

    @abstractmethod
    def place_market_order(self, symbol: str, is_buy: bool, size: float, price: float) -> OrderResult:
        """Размещение рыночного ордера"""
        pass

    @abstractmethod
    def close_position(self, symbol: str) -> OrderResult:
        """Закрытие позиции"""
        pass

    @abstractmethod
    def close_all_positions(self, positions: Dict[str, float]) -> Dict[str, OrderResult]:
        """Закрытие всех позиций"""
        pass

    @abstractmethod
    def validate_order_size(self, symbol: str, size: float) -> Tuple[bool, float, str]:
        """Валидация размера ордера"""
        pass


class IRiskManager(ABC):
    """Интерфейс для управления рисками"""

    @abstractmethod
    def update_leverage(self, symbol: str, leverage: int) -> bool:
        """Обновление плеча"""
        pass

    @abstractmethod
    def get_current_leverages(self) -> Dict[str, float]:
        """Получение текущих плечей"""
        pass

    @abstractmethod
    def check_leverage_compliance(self, required_btc: int, required_shorts: int, shorts: List[str]) -> Dict[str, bool]:
        """Проверка соответствия плечей"""
        pass

    @abstractmethod
    def force_leverage_compliance(self, required_btc: int, required_shorts: int, shorts: List[str]) -> bool:
        """Принудительное приведение плечей в соответствие"""
        pass


class IPerformanceMonitor(ABC):
    """Интерфейс для мониторинга производительности"""

    @abstractmethod
    def track_latency(self, operation: str, duration: float) -> None:
        """Отслеживание времени выполнения операций"""
        pass

    @abstractmethod
    def track_success_rate(self, operation: str, success: bool) -> None:
        """Отслеживание успешности операций"""
        pass

    @abstractmethod
    def track_pnl(self, unrealized: float, realized: float) -> None:
        """Отслеживание PnL"""
        pass

    @abstractmethod
    def track_order_placed(self) -> None:
        """Отслеживание размещенных ордеров"""
        pass

    @abstractmethod
    def track_rebalance_executed(self) -> None:
        """Отслеживание выполненных ребалансировок"""
        pass

    @abstractmethod
    def get_metrics(self) -> Dict[str, float]:
        """Получение метрик производительности"""
        pass
