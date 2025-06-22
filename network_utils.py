"""
Сетевые утилиты для обработки ошибок и повторных попыток
"""

from typing import Callable, Any, Optional, Dict, Type
from functools import wraps
import time
import random
import logging
from logger_config import setup_unified_logger
from exceptions import NetworkError, APIError


class NetworkRetryConfig:
    """Конфигурация для повторных попыток"""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        """Рассчитать задержку для попытки"""
        delay = self.base_delay * (self.exponential_base ** attempt)
        delay = min(delay, self.max_delay)

        if self.jitter:
            delay *= (0.5 + random.random() * 0.5)

        return delay


def with_retry(
    config: Optional[NetworkRetryConfig] = None,
    exceptions: tuple = (Exception,),
    logger: Optional[logging.Logger] = None
):
    """Декоратор для повторных попыток при ошибках"""
    if config is None:
        config = NetworkRetryConfig()

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(config.max_retries + 1):
                try:
                    return func(*args, **kwargs)

                except exceptions as exc:
                    last_exception = exc

                    if attempt == config.max_retries:
                        if logger:
                            logger.error(
                                f"Function {func.__name__} failed after {config.max_retries + 1} attempts: {exc}")
                        raise

                    delay = config.get_delay(attempt)
                    if logger:
                        logger.warning(
                            f"Function {func.__name__} failed (attempt {attempt + 1}/{config.max_retries + 1}), "
                            f"retrying in {delay:.2f}s: {exc}")

                    time.sleep(delay)

            # Это не должно выполняться, но для безопасности
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


class PriceValidator:
    """Валидатор цен для проверки разумности значений"""

    def __init__(
        self,
        min_price: float = 0.0001,
        max_price: float = 1000000.0,
        max_change_percent: float = 50.0
    ):
        self.min_price = min_price
        self.max_price = max_price
        self.max_change_percent = max_change_percent
        self._last_prices: Dict[str, float] = {}

    def validate_price(self, symbol: str, price: float, previous_price: Optional[float] = None) -> bool:
        """Проверка разумности цены"""
        # Проверка базовых границ
        if not (self.min_price <= price <= self.max_price):
            return False

        # Проверка изменения относительно предыдущей цены
        if previous_price is None:
            previous_price = self._last_prices.get(symbol)

        if previous_price is not None and previous_price > 0:
            change_percent = abs(price - previous_price) / previous_price * 100
            if change_percent > self.max_change_percent:
                return False

        # Сохраняем цену для следующей проверки
        self._last_prices[symbol] = price
        return True

    def get_last_price(self, symbol: str) -> Optional[float]:
        """Получить последнюю валидную цену"""
        return self._last_prices.get(symbol)


class CircuitBreaker:
    """Circuit breaker для предотвращения каскадных сбоев"""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: Type[Exception] = Exception
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN

    def __call__(self, func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if self.state == 'OPEN':
                if self._should_attempt_reset():
                    self.state = 'HALF_OPEN'
                else:
                    raise Exception("Circuit breaker is OPEN")

            try:
                result = func(*args, **kwargs)
                self._on_success()
                return result

            except self.expected_exception:
                self._on_failure()
                raise

        return wrapper

    def _should_attempt_reset(self) -> bool:
        """Проверить, следует ли попытаться сбросить circuit breaker"""
        return (
            self.last_failure_time is not None and
            time.time() - self.last_failure_time >= self.recovery_timeout
        )

    def _on_success(self):
        """Обработка успешного выполнения"""
        self.failure_count = 0
        self.state = 'CLOSED'

    def _on_failure(self):
        """Обработка сбоя"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = 'OPEN'


# Предустановленные конфигурации
AGGRESSIVE_RETRY = NetworkRetryConfig(max_retries=5, base_delay=0.5, max_delay=30.0)
CONSERVATIVE_RETRY = NetworkRetryConfig(max_retries=3, base_delay=2.0, max_delay=60.0)
QUICK_RETRY = NetworkRetryConfig(max_retries=2, base_delay=0.1, max_delay=5.0)

# Предконфигурированные экземпляры
default_retry_config = NetworkRetryConfig(
    max_retries=3,
    base_delay=1.0,
    max_delay=10.0,
    backoff_multiplier=2.0,
    timeout=30.0
)

api_retry_config = NetworkRetryConfig(
    max_retries=2,
    base_delay=0.5,
    max_delay=5.0,
    backoff_multiplier=1.5,
    timeout=15.0
)

price_validator = PriceValidator()
