"""
Компонент для мониторинга производительности торгового бота
Отслеживает метрики, латентность и успешность операций
"""

import time
from typing import Dict
from collections import defaultdict, deque
from dataclasses import dataclass, field
from logger_config import setup_unified_logger
from interfaces import IPerformanceMonitor


@dataclass
class OperationMetrics:
    """Метрики операции"""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_latency: float = 0.0
    max_latency: float = 0.0
    min_latency: float = float('inf')
    recent_latencies: deque = field(default_factory=lambda: deque(maxlen=100))

    @property
    def success_rate(self) -> float:
        """Процент успешных операций"""
        return (self.successful_calls / self.total_calls * 100) if self.total_calls > 0 else 0.0

    @property
    def avg_latency(self) -> float:
        """Средняя латентность"""
        return self.total_latency / self.total_calls if self.total_calls > 0 else 0.0

    @property
    def recent_avg_latency(self) -> float:
        """Средняя латентность последних операций"""
        if not self.recent_latencies:
            return 0.0
        return sum(self.recent_latencies) / len(self.recent_latencies)


@dataclass
class PnLMetrics:
    """Метрики PnL"""
    total_unrealized: float = 0.0
    total_realized: float = 0.0
    max_unrealized: float = 0.0
    min_unrealized: float = 0.0
    updates_count: int = 0
    last_update: float = 0.0

    @property
    def total_pnl(self) -> float:
        """Общий PnL"""
        return self.total_unrealized + self.total_realized


class PerformanceMonitor(IPerformanceMonitor):
    """Монитор производительности"""

    def __init__(self):
        self.logger = setup_unified_logger("performance_monitor")
        self.operation_metrics: Dict[str, OperationMetrics] = defaultdict(OperationMetrics)
        self.pnl_metrics = PnLMetrics()
        self.start_time = time.time()

        # Счетчики для различных событий
        self.api_calls_count = 0
        self.orders_placed = 0
        self.rebalances_executed = 0
        self.errors_count = 0

        self.logger.info("[INIT] Performance monitor initialized")

    def track_latency(self, operation: str, duration: float) -> None:
        """Отслеживание времени выполнения операций"""
        metrics = self.operation_metrics[operation]

        metrics.total_calls += 1
        metrics.total_latency += duration
        metrics.recent_latencies.append(duration)

        if duration > metrics.max_latency:
            metrics.max_latency = duration
        if duration < metrics.min_latency:
            metrics.min_latency = duration

        self.api_calls_count += 1

        # Логируем медленные операции
        if duration > 5.0:  # Более 5 секунд
            self.logger.warning(f"[PERF] Slow operation {operation}: {duration:.3f}s")
        elif duration > 2.0:  # Более 2 секунд
            self.logger.info(f"[PERF] {operation}: {duration:.3f}s")

    def track_success_rate(self, operation: str, success: bool) -> None:
        """Отслеживание успешности операций"""
        metrics = self.operation_metrics[operation]

        if success:
            metrics.successful_calls += 1
        else:
            metrics.failed_calls += 1
            self.errors_count += 1

        # Логируем проблемы с успешностью
        current_success_rate = metrics.success_rate
        if metrics.total_calls >= 10 and current_success_rate < 90:
            self.logger.warning(f"[PERF] Low success rate for {operation}: {current_success_rate:.1f}%")

    def track_pnl(self, unrealized: float, realized: float) -> None:
        """Отслеживание PnL"""
        self.pnl_metrics.total_unrealized = unrealized
        self.pnl_metrics.total_realized = realized
        self.pnl_metrics.updates_count += 1
        self.pnl_metrics.last_update = time.time()

        # Обновляем экстремумы
        if unrealized > self.pnl_metrics.max_unrealized:
            self.pnl_metrics.max_unrealized = unrealized
        if unrealized < self.pnl_metrics.min_unrealized:
            self.pnl_metrics.min_unrealized = unrealized

        self.logger.debug(f"[PNL] Unrealized: ${unrealized:.2f}, Realized: ${realized:.2f}")

    def track_order_placed(self) -> None:
        """Отслеживание размещенных ордеров"""
        self.orders_placed += 1
        self.logger.debug(f"[PERF] Orders placed: {self.orders_placed}")

    def track_rebalance_executed(self) -> None:
        """Отслеживание выполненных ребалансировок"""
        self.rebalances_executed += 1
        self.logger.info(f"[PERF] Rebalances executed: {self.rebalances_executed}")

    def get_metrics(self) -> Dict[str, float]:
        """Получение метрик производительности"""
        uptime = time.time() - self.start_time

        metrics = {
            'uptime_hours': uptime / 3600,
            'total_api_calls': self.api_calls_count,
            'orders_placed': self.orders_placed,
            'rebalances_executed': self.rebalances_executed,
            'errors_count': self.errors_count,
            'api_calls_per_hour': self.api_calls_count / (uptime / 3600) if uptime > 0 else 0,
            'error_rate_percent': (self.errors_count / self.api_calls_count * 100) if self.api_calls_count > 0 else 0,
            'total_pnl': self.pnl_metrics.total_pnl,
            'unrealized_pnl': self.pnl_metrics.total_unrealized,
            'realized_pnl': self.pnl_metrics.total_realized,
            'max_unrealized_pnl': self.pnl_metrics.max_unrealized,
            'min_unrealized_pnl': self.pnl_metrics.min_unrealized
        }

        # Добавляем метрики по операциям
        for operation, op_metrics in self.operation_metrics.items():
            prefix = f"{operation}_"
            metrics.update({
                f"{prefix}success_rate": op_metrics.success_rate,
                f"{prefix}avg_latency": op_metrics.avg_latency,
                f"{prefix}recent_avg_latency": op_metrics.recent_avg_latency,
                f"{prefix}max_latency": op_metrics.max_latency,
                f"{prefix}total_calls": op_metrics.total_calls
            })

        return metrics

    def log_performance_summary(self) -> None:
        """Логирование сводки производительности"""
        metrics = self.get_metrics()

        self.logger.info("=" * 60)
        self.logger.info("[PERF] Performance Summary")
        self.logger.info(f"[PERF] Uptime: {metrics['uptime_hours']:.1f} hours")
        self.logger.info(f"[PERF] API Calls: {metrics['total_api_calls']} ({metrics['api_calls_per_hour']:.1f}/hour)")
        self.logger.info(f"[PERF] Orders: {metrics['orders_placed']}, Rebalances: {metrics['rebalances_executed']}")
        self.logger.info(f"[PERF] Error Rate: {metrics['error_rate_percent']:.1f}%")
        self.logger.info(f"[PERF] PnL: ${metrics['total_pnl']:.2f} (Unrealized: ${metrics['unrealized_pnl']:.2f})")

        # Топ медленных операций
        slow_operations = []
        for operation, op_metrics in self.operation_metrics.items():
            if op_metrics.total_calls > 0:
                slow_operations.append((operation, op_metrics.avg_latency))

        slow_operations.sort(key=lambda x: x[1], reverse=True)

        if slow_operations:
            self.logger.info("[PERF] Slowest operations:")
            for operation, latency in slow_operations[:5]:
                self.logger.info(f"[PERF]   {operation}: {latency:.3f}s avg")

        self.logger.info("=" * 60)

    def reset_metrics(self) -> None:
        """Сброс метрик"""
        self.operation_metrics.clear()
        self.pnl_metrics = PnLMetrics()
        self.start_time = time.time()
        self.api_calls_count = 0
        self.orders_placed = 0
        self.rebalances_executed = 0
        self.errors_count = 0

        self.logger.info("[PERF] Metrics reset")
