"""
Рефакторированный трейдер с новой модульной архитектурой
Использует инжекцию зависимостей и разделение ответственности
"""

import time
import signal
import sys
import traceback
from typing import Dict
from logger_config import setup_unified_logger, log_session_end
from config_manager import ConfigManager
from state_manager import StateManager

# Новые модульные компоненты
from market_data_provider import HyperliquidMarketDataProvider
from position_provider import HyperliquidPositionProvider
from order_executor import HyperliquidOrderExecutor
from performance_monitor import PerformanceMonitor
from risk_manager import HyperliquidRiskManager
from strategy import LongShortStrategy

# Для совместимости с existing metadata
from asset_metadata import get_asset_metadata_provider


class HyperliquidTrader:
    """Трейдер с модульной архитектурой"""

    def __init__(self, config_path: str = 'config.json'):
        self.logger = setup_unified_logger("trader")
        self.logger.info('=== Hyperliquid Trader Starting ===')

        self.running = False
        self.config_path = config_path

        try:
            # Инициализация базовых компонентов
            self.config_manager = ConfigManager(config_path)
            self.state_manager = StateManager()

            # Получаем провайдер метаданных активов
            self.asset_metadata_provider = get_asset_metadata_provider()
            asset_meta = self.asset_metadata_provider.get_asset_meta()

            # Создаем новые модульные компоненты
            self.market_data_provider = HyperliquidMarketDataProvider()
            self.position_provider = HyperliquidPositionProvider(self.config_manager.account_address)
            self.order_executor = HyperliquidOrderExecutor(
                self.config_manager.secret_key,
                self.config_manager.account_address,
                asset_meta
            )
            self.performance_monitor = PerformanceMonitor()

            # Risk Manager с asset metadata и API delays
            api_delays = self.config_manager.get('api_delays', {})
            self.risk_manager = HyperliquidRiskManager(
                self.config_manager.secret_key,
                self.config_manager.account_address,
                asset_meta,
                api_delays
            )

            # Создаем стратегию с инжекцией зависимостей
            self.strategy = LongShortStrategy(
                market_data_provider=self.market_data_provider,
                position_provider=self.position_provider,
                order_executor=self.order_executor,
                performance_monitor=self.performance_monitor,
                risk_manager=self.risk_manager,
                ratio_target=self.config_manager.ratio_target,
                reserve_percent=self.config_manager.reserve_usd_percent,
                rebalance_threshold=self.config_manager.rebalance_threshold,
                shorts_symbols=self.config_manager.shorts
            )

            # Настройка обработчиков сигналов
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)

            self.logger.info('=== Components initialized successfully ===')

        except Exception as e:
            self.logger.error(f'FATAL: Initialization failed: {e}')
            self.logger.error(traceback.format_exc())
            sys.exit(1)

    def _signal_handler(self, signum, frame):
        """Обработка сигналов для graceful shutdown"""
        self.logger.info(f'🛑 Signal {signum} received, shutting down gracefully...')
        self.running = False
        self.logger.info('⏳ Please wait for current operations to complete...')

    def run_trading_cycle(self) -> bool:
        """Выполнение одного цикла торговли"""
        cycle_start = time.time()

        try:
            self.logger.info('--- Starting trading cycle ---')

            # Отслеживаем время выполнения цикла
            with self._track_operation("trading_cycle"):
                success = self.strategy.run_strategy_cycle()

            # Сохраняем состояние
            self.state_manager.save_state()

            cycle_duration = time.time() - cycle_start
            self.performance_monitor.track_latency("full_cycle", cycle_duration)

            if success:
                self.logger.info(f'Trading cycle completed successfully in {cycle_duration:.3f}s')
            else:
                self.logger.error(f'Trading cycle failed after {cycle_duration:.3f}s')

            return success

        except Exception as e:
            cycle_duration = time.time() - cycle_start
            self.logger.error(f'Trading cycle exception after {cycle_duration:.3f}s: {e}')
            self.logger.error(traceback.format_exc())
            self.performance_monitor.track_success_rate("trading_cycle", False)
            return False

    def _track_operation(self, operation_name: str):
        """Context manager для отслеживания операций"""
        class OperationTracker:
            def __init__(self, monitor, operation):
                self.monitor = monitor
                self.operation = operation
                self.start_time = None

            def __enter__(self):
                self.start_time = time.time()
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                duration = time.time() - (self.start_time or 0.0)
                success = exc_type is None
                self.monitor.track_latency(self.operation, duration)
                self.monitor.track_success_rate(self.operation, success)

        return OperationTracker(self.performance_monitor, operation_name)

    def run_main_loop(self, sleep_duration: int = 300) -> None:
        """Основной цикл работы трейдера"""
        self.running = True
        cycle_count = 0

        self.logger.info(f'Starting main loop with {sleep_duration}s intervals')

        try:
            while self.running:
                cycle_count += 1
                self.logger.info(f'=== Cycle #{cycle_count} ===')

                # Выполняем цикл торговли
                success = self.run_trading_cycle()

                # Логируем метрики каждые 10 циклов
                if cycle_count % 10 == 0:
                    self.performance_monitor.log_performance_summary()

                if not success:
                    self.logger.warning('Cycle failed, but continuing...')

                # Ожидание между циклами с возможностью прерывания
                if self.running:
                    self.logger.info(f'Sleeping for {sleep_duration}s... (Press Ctrl+C to stop)')
                    # Разбиваем длительный sleep на короткие интервалы для возможности прерывания
                    for i in range(sleep_duration):
                        if not self.running:
                            break
                        time.sleep(1)

        except KeyboardInterrupt:
            self.logger.info('Keyboard interrupt received')
        except Exception as e:
            self.logger.error(f'Main loop exception: {e}')
            self.logger.error(traceback.format_exc())
        finally:
            self.cleanup()

    def cleanup(self) -> None:
        """Очистка ресурсов при завершении"""
        self.logger.info('=== Cleaning up ===')

        try:
            # Сохраняем состояние
            self.state_manager.save_state()

            # Финальная сводка производительности
            self.performance_monitor.log_performance_summary()

            # Очищаем ресурсы
            if hasattr(self, 'asset_metadata_provider'):
                # Провайдер метаданных не требует специальной очистки
                pass

            self.logger.info('=== Cleanup completed ===')

        except Exception as e:
            self.logger.error(f'Cleanup error: {e}')
        finally:
            log_session_end()

    def close_all_positions(self) -> bool:
        """Закрытие всех позиций"""
        self.logger.info('=== Closing all positions ===')

        try:
            success = self.strategy.close_all_positions()

            if success:
                self.logger.info('All positions closed successfully')
            else:
                self.logger.error('Failed to close some positions')

            return success

        except Exception as e:
            self.logger.error(f'Error closing positions: {e}')
            return False

    def get_portfolio_status(self) -> Dict:
        """Получение детального статуса портфеля с leverage информацией"""
        try:
            portfolio_state = self.strategy.get_portfolio_state()
            metrics = self.performance_monitor.get_metrics()

            # Получаем детальную информацию о позициях и leverage
            position_details = self.risk_manager.get_position_details_with_leverage()
            current_leverages = self.risk_manager.get_current_leverages()

            # Проверяем compliance
            compliance = self.risk_manager.check_leverage_compliance(
                self.config_manager.leverage_btc,
                self.config_manager.leverage_shorts,
                self.config_manager.shorts
            )

            # Получаем цены для расчетов
            all_symbols = ["BTC"] + self.config_manager.shorts
            prices = self.market_data_provider.get_prices(all_symbols)

            # Рассчитываем стоимости позиций
            btc_value = portfolio_state.btc_position * prices.get("BTC", 0.0)
            shorts_value = sum(
                abs(portfolio_state.shorts_positions.get(symbol, 0.0)) * prices.get(symbol, 0.0)
                for symbol in self.config_manager.shorts
            )

            # Формируем открытые позиции
            open_positions = {}
            for symbol, size in {**{"BTC": portfolio_state.btc_position}, **portfolio_state.shorts_positions}.items():
                if abs(size) > 1e-8:
                    open_positions[symbol] = size

            status = {
                'nav': portfolio_state.nav,
                'nav_for_trading': portfolio_state.nav * (1 - self.config_manager.reserve_usd_percent),
                'reserve_amount': portfolio_state.nav * self.config_manager.reserve_usd_percent,
                'reserve_percent': self.config_manager.reserve_usd_percent,
                'btc_position': portfolio_state.btc_position,
                'shorts_positions': portfolio_state.shorts_positions,
                'btc_value_usd': btc_value,
                'shorts_value_usd': shorts_value,
                'btc_margin': portfolio_state.btc_margin,
                'shorts_margin': portfolio_state.shorts_margin,
                'position_ratio': portfolio_state.position_ratio,
                'target_ratio': self.config_manager.ratio_target,
                'margin_usage_percent': portfolio_state.margin_usage_percent,
                'available_balance': portfolio_state.available_balance,
                'open_positions': open_positions,
                'prices': prices,
                'margin_summary': position_details.get('margin_summary', {}),
                'position_details': position_details.get('positions', {}),
                'current_leverages': current_leverages,
                'leverage_compliance': compliance,
                'performance_metrics': metrics
            }

            # Рассчитываем margin ratio
            margin_summary = status['margin_summary']
            btc_margin = margin_summary.get('btc_margin_used', 0.0)
            shorts_margin = margin_summary.get('shorts_margin_used', 0.0)
            status['margin_ratio'] = btc_margin / shorts_margin if shorts_margin > 1e-6 else 0.0

            # Логируем статус
            self.logger.info('=== Portfolio Status ===')
            self.logger.info(f'NAV: ${status["nav"]:.2f}')
            self.logger.info(f'BTC Position: {status["btc_position"]:.6f} (${status["btc_value_usd"]:.2f})')
            self.logger.info(f'Shorts Value: ${status["shorts_value_usd"]:.2f}')
            self.logger.info(
                f'Position Ratio (by margin): {status["position_ratio"]:.2f} (Target: {status["target_ratio"]:.2f})')
            self.logger.info(
                f'BTC Margin: ${portfolio_state.btc_margin:.2f}, Shorts Margin: ${portfolio_state.shorts_margin:.2f}')
            self.logger.info(f'Margin Usage: {status["margin_usage_percent"]:.1f}%')

            # Логируем leverage compliance
            non_compliant = [symbol for symbol, compliant in compliance.items() if not compliant]
            if non_compliant:
                self.logger.warning(f'Leverage non-compliance: {non_compliant}')
            else:
                self.logger.info('All leverages compliant')

            return status

        except Exception as e:
            self.logger.error(f'Error getting portfolio status: {e}')
            return {}

    def force_rebalance(self) -> bool:
        """Принудительная ребалансировка"""
        self.logger.info('=== Force Rebalance ===')

        try:
            # Используем стратегию для принудительной ребалансировки
            portfolio_state = self.strategy.get_portfolio_state()
            decision = self.strategy.calculate_rebalance_decision(portfolio_state)

            # Принудительно выполняем ребалансировку
            decision.should_rebalance = True
            decision.reason = "Force rebalance requested"

            success = self.strategy.execute_rebalance(decision, portfolio_state)

            if success:
                self.logger.info('Force rebalance completed successfully')
            else:
                self.logger.error('Force rebalance failed')

            return success

        except Exception as e:
            self.logger.error(f'Force rebalance error: {e}')
            return False


# Удалена дублирующаяся точка входа - используйте main.py для запуска
