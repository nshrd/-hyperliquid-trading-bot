"""
Рефакторированная стратегия для долго/коротких позиций
Использует новую модульную архитектуру с инжекцией зависимостей
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from logger_config import setup_unified_logger
from interfaces import (
    IMarketDataProvider, 
    IPositionProvider, 
    IOrderExecutor, 
    IPerformanceMonitor,
    IRiskManager,
    OrderResult
)

@dataclass
class RebalanceDecision:
    """Решение о ребалансировке"""
    should_rebalance: bool
    btc_target_usd: float
    shorts_target_usd: float
    btc_current_usd: float
    shorts_current_usd: float
    current_ratio: float
    deviation_percent: float
    reason: str = ""

@dataclass
class PortfolioState:
    """Состояние портфеля"""
    nav: float
    btc_position: float
    shorts_positions: Dict[str, float]
    btc_value_usd: float
    shorts_value_usd: float
    btc_margin: float
    shorts_margin: float
    position_ratio: float  # Рассчитывается как btc_margin / shorts_margin
    margin_usage_percent: float
    available_balance: float

class LongShortStrategy:
    """
    Стратегия долго/коротких позиций
    Поддерживает фиксированное соотношение между BTC и шортами
    """
    
    def __init__(
        self,
        market_data_provider: IMarketDataProvider,
        position_provider: IPositionProvider,
        order_executor: IOrderExecutor,
        performance_monitor: IPerformanceMonitor,
        risk_manager: Optional[IRiskManager] = None,
        ratio_target: float = 2.0,
        reserve_percent: float = 0.05,
        rebalance_threshold: float = 0.10,
        shorts_symbols: Optional[List[str]] = None
    ):
        self.logger = setup_unified_logger("strategy")
        
        # Инжектированные зависимости
        self.market_data = market_data_provider
        self.position_provider = position_provider
        self.order_executor = order_executor
        self.performance_monitor = performance_monitor
        self.risk_manager = risk_manager
        
        # Параметры стратегии
        self.ratio_target = ratio_target
        self.reserve_percent = reserve_percent
        self.rebalance_threshold = rebalance_threshold
        self.shorts_symbols = shorts_symbols if shorts_symbols is not None else ["ZK", "STRK"]
        
        self.logger.info(f"[INIT] Strategy initialized - Target ratio: {ratio_target}, Reserve: {reserve_percent:.1%}")
    
    def get_portfolio_state(self) -> PortfolioState:
        """Получение текущего состояния портфеля"""
        # Получаем позиции
        positions = self.position_provider.get_positions()
        account_summary = self.position_provider.get_account_summary()
        
        # Получаем цены
        all_symbols = ["BTC"] + self.shorts_symbols
        prices = self.market_data.get_prices(all_symbols)
        
        # Рассчитываем стоимости позиций
        btc_position = positions.get("BTC", 0.0)
        btc_value_usd = btc_position * prices.get("BTC", 0.0)
        
        shorts_positions = {symbol: positions.get(symbol, 0.0) for symbol in self.shorts_symbols}
        shorts_value_usd = sum(
            abs(pos) * prices.get(symbol, 0.0) 
            for symbol, pos in shorts_positions.items()
        )
        
        # Получаем детальную информацию о позициях для расчета margin
        position_details = self.position_provider.get_position_details()
        
        # Рассчитываем margin для BTC и шортов
        btc_margin = 0.0
        shorts_margin = 0.0
        
        for pos_info in position_details:
            if pos_info.symbol == "BTC":
                btc_margin += pos_info.margin_used
            elif pos_info.symbol in self.shorts_symbols:
                shorts_margin += pos_info.margin_used
        
        # Рассчитываем метрики
        nav = account_summary.get('account_value', 0.0)
        # ВАЖНО: position_ratio рассчитывается по margin, а не по стоимости позиций!
        position_ratio = btc_margin / shorts_margin if shorts_margin > 0 else 999.0
        
        margin_used = account_summary.get('total_margin_used', 0.0)
        margin_usage_percent = (margin_used / nav * 100) if nav > 0 else 0.0
        
        return PortfolioState(
            nav=nav,
            btc_position=btc_position,
            shorts_positions=shorts_positions,
            btc_value_usd=btc_value_usd,
            shorts_value_usd=shorts_value_usd,
            btc_margin=btc_margin,
            shorts_margin=shorts_margin,
            position_ratio=position_ratio,
            margin_usage_percent=margin_usage_percent,
            available_balance=nav - margin_used
        )
    
    def calculate_rebalance_decision(self, portfolio: PortfolioState) -> RebalanceDecision:
        """Расчет необходимости ребалансировки"""
        # Рассчитываем доступные средства для торговли
        available_for_trading = portfolio.nav * (1.0 - self.reserve_percent)
        
        # Целевые размеры позиций
        total_target = available_for_trading
        btc_target_usd = total_target * self.ratio_target / (self.ratio_target + 1)
        shorts_target_usd = total_target * 1 / (self.ratio_target + 1)
        
        # Отклонение от целевого соотношения
        if self.ratio_target > 0:
            deviation_percent = abs(portfolio.position_ratio - self.ratio_target) / self.ratio_target
        else:
            deviation_percent = 0.0
        
        should_rebalance = deviation_percent > self.rebalance_threshold
        
        reason = ""
        if should_rebalance:
            if portfolio.position_ratio > self.ratio_target:
                reason = f"Ratio too high: {portfolio.position_ratio:.2f} > {self.ratio_target:.2f}"
            else:
                reason = f"Ratio too low: {portfolio.position_ratio:.2f} < {self.ratio_target:.2f}"
        
        return RebalanceDecision(
            should_rebalance=should_rebalance,
            btc_target_usd=btc_target_usd,
            shorts_target_usd=shorts_target_usd,
            btc_current_usd=portfolio.btc_value_usd,
            shorts_current_usd=portfolio.shorts_value_usd,
            current_ratio=portfolio.position_ratio,
            deviation_percent=deviation_percent,
            reason=reason
        )
    
    def execute_rebalance(self, decision: RebalanceDecision, portfolio: PortfolioState) -> bool:
        """Выполнение ребалансировки"""
        if not decision.should_rebalance:
            return True
        
        self.logger.info(f"[REBALANCE] Starting rebalance: {decision.reason}")
        self.logger.info(f"[REBALANCE] Current - BTC: ${portfolio.btc_value_usd:.2f}, Shorts: ${portfolio.shorts_value_usd:.2f}")
        self.logger.info(f"[REBALANCE] Target - BTC: ${decision.btc_target_usd:.2f}, Shorts: ${decision.shorts_target_usd:.2f}")
        
        success = True
        prices = self.market_data.get_prices(["BTC"] + self.shorts_symbols)
        
        # Ребалансировка BTC
        btc_diff_usd = decision.btc_target_usd - decision.btc_current_usd
        if abs(btc_diff_usd) > 5.0:  # Минимальный порог $5
            btc_price = prices.get("BTC", 0.0)
            if btc_price <= 0:
                self.logger.error("[REBALANCE] Invalid BTC price, skipping BTC rebalance")
                success = False
            else:
                btc_size_diff = btc_diff_usd / btc_price
                is_buy = btc_size_diff > 0
                
                result = self.order_executor.place_market_order(
                    "BTC", is_buy, abs(btc_size_diff), btc_price
                )
            
                if result.success:
                    self.logger.info(f"[REBALANCE] BTC order successful: {'BUY' if is_buy else 'SELL'} {abs(btc_size_diff):.6f}")
                    self.performance_monitor.track_order_placed()
                else:
                    self.logger.error(f"[REBALANCE] BTC order failed: {result.error_message}")
                    success = False
        
        # Ребалансировка шортов
        shorts_diff_usd = decision.shorts_target_usd - decision.shorts_current_usd
        if abs(shorts_diff_usd) > 5.0:  # Минимальный порог $5
            self.logger.info(f"[REBALANCE] Shorts adjustment needed: ${shorts_diff_usd:.2f}")
            
            # Получаем текущие позиции шортов
            current_shorts = portfolio.shorts_positions
            
            # Рассчитываем целевые позиции для каждого символа
            target_shorts_per_symbol = decision.shorts_target_usd / len(self.shorts_symbols)
            
            for symbol in self.shorts_symbols:
                symbol_price = prices.get(symbol, 0.0)
                if symbol_price == 0:
                    self.logger.warning(f"[REBALANCE] No price for {symbol}, skipping")
                    continue
                
                # Текущая позиция в USD (отрицательная для шортов)
                current_position_size = current_shorts.get(symbol, 0.0)
                current_position_usd = abs(current_position_size) * symbol_price
                
                # Целевая позиция в USD (всегда положительная величина)
                target_position_usd = target_shorts_per_symbol
                
                # Разница в USD
                position_diff_usd = target_position_usd - current_position_usd
                
                self.logger.debug(f"[REBALANCE] {symbol}: Current ${current_position_usd:.2f}, Target ${target_position_usd:.2f}, Diff ${position_diff_usd:.2f}")
                
                if abs(position_diff_usd) > 2.0:  # Минимальный порог $2 на символ
                    # Рассчитываем размер ордера
                    order_size = abs(position_diff_usd) / symbol_price
                    
                    # Определяем направление ордера
                    if position_diff_usd > 0:
                        # Нужно увеличить шорт позицию (продать больше)
                        is_buy = False
                        action = "SELL"
                    else:
                        # Нужно уменьшить шорт позицию (купить обратно)
                        is_buy = True
                        action = "BUY"
                    
                    self.logger.info(f"[REBALANCE] {symbol}: {action} {order_size:.6f} @ ${symbol_price:.4f}")
                    
                    result = self.order_executor.place_market_order(
                        symbol, is_buy, order_size, symbol_price
                    )
                    
                    if result.success:
                        self.logger.info(f"[REBALANCE] {symbol} order successful: {action} {order_size:.6f}")
                        self.performance_monitor.track_order_placed()
                    else:
                        self.logger.error(f"[REBALANCE] {symbol} order failed: {result.error_message}")
                        success = False
                else:
                    self.logger.debug(f"[REBALANCE] {symbol}: No adjustment needed (${position_diff_usd:.2f})")
        
        if success:
            self.performance_monitor.track_rebalance_executed()
            self.logger.info("[REBALANCE] Rebalance completed successfully")
        else:
            self.logger.error("[REBALANCE] Rebalance completed with errors")
        
        return success
    
    def run_strategy_cycle(self) -> bool:
        """Выполнение одного цикла стратегии"""
        try:
            # Получаем состояние портфеля
            portfolio = self.get_portfolio_state()
            
            # Отслеживаем PnL
            total_unrealized = portfolio.btc_value_usd + portfolio.shorts_value_usd - portfolio.nav
            self.performance_monitor.track_pnl(total_unrealized, 0.0)  # Realized = 0 для простоты
            
            # Проверяем и исправляем leverage compliance ПЕРЕД ребалансировкой
            if self.risk_manager:
                try:
                    from config_manager import ConfigManager
                    config = ConfigManager()
                    
                    compliance = self.risk_manager.check_leverage_compliance(
                        config.leverage_btc,
                        config.leverage_shorts,
                        config.shorts
                    )
                    
                    non_compliant = [symbol for symbol, compliant in compliance.items() if not compliant]
                    if non_compliant:
                        self.logger.warning(f"[STRATEGY] ⚠️  LEVERAGE NON-COMPLIANCE DETECTED: {non_compliant}")
                        self.logger.warning("[STRATEGY] 🔄 INITIATING FULL RESET: All positions will be closed and reopened!")
                        self.logger.info("[STRATEGY] This process will: 1) Close ALL positions 2) Set correct leverages 3) Reopen positions")
                        
                        success = self.risk_manager.force_leverage_compliance(
                            config.leverage_btc,
                            config.leverage_shorts,
                            config.shorts
                        )
                        
                        if success:
                            self.logger.info("[STRATEGY] ✅ Leverage compliance FULL RESET completed successfully")
                            self.logger.info("[STRATEGY] All positions have been reopened with correct leverages")
                            # После полной перенастройки пропускаем обычную ребалансировку в этом цикле
                            return True
                        else:
                            self.logger.error("[STRATEGY] ❌ FULL RESET failed - manual intervention required!")
                            return False
                            
                except Exception as e:
                    self.logger.error(f"[STRATEGY] Error checking leverage compliance: {e}")
            
            # Принимаем решение о ребалансировке
            decision = self.calculate_rebalance_decision(portfolio)
            
            # Логируем состояние
            self.logger.debug(f"[STRATEGY] NAV: ${portfolio.nav:.2f}, Ratio: {portfolio.position_ratio:.2f} (target: {self.ratio_target:.2f})")
            self.logger.debug(f"[STRATEGY] Deviation: {decision.deviation_percent:.1%}, Threshold: {self.rebalance_threshold:.1%}")
            
            # Выполняем ребалансировку если необходимо
            if decision.should_rebalance:
                return self.execute_rebalance(decision, portfolio)
            else:
                self.logger.debug("[STRATEGY] No rebalancing needed")
                return True
                
        except Exception as e:
            self.logger.error(f"[STRATEGY] Strategy cycle failed: {e}")
            return False
    
    def close_all_positions(self) -> bool:
        """Закрытие всех позиций"""
        self.logger.info("[STRATEGY] Closing all positions")
        
        positions = self.position_provider.get_positions()
        open_positions = {k: v for k, v in positions.items() if abs(v) > 1e-8}
        
        if not open_positions:
            self.logger.info("[STRATEGY] No open positions to close")
            return True
        
        results = self.order_executor.close_all_positions(open_positions)
        
        success = all(result.success for result in results.values())
        
        if success:
            self.logger.info("[STRATEGY] All positions closed successfully")
        else:
            failed = [symbol for symbol, result in results.items() if not result.success]
            self.logger.error(f"[STRATEGY] Failed to close positions: {failed}")
        
        return success
