"""
Компонент для управления рисками и leverage на Hyperliquid
Реализует интерфейс IRiskManager
"""

import time
from typing import Dict, List, Tuple
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils.constants import MAINNET_API_URL
from eth_account import Account
from logger_config import setup_unified_logger
from interfaces import IRiskManager

class HyperliquidRiskManager(IRiskManager):
    """Менеджер рисков для Hyperliquid"""
    
    def __init__(self, secret_key: str, account_address: str, asset_meta: Dict[str, dict] = None, api_delays: Dict[str, int] = None):
        self.logger = setup_unified_logger("risk_manager")
        self.wallet = Account.from_key(secret_key)
        self.account_address = account_address
        self.exchange = Exchange(self.wallet, base_url=MAINNET_API_URL, account_address=account_address)
        self.info = Info(MAINNET_API_URL, skip_ws=True)
        self.asset_meta = asset_meta or {}
        
        # Настройка задержек API
        delays = api_delays or {}
        self.order_processing_delay = delays.get('order_processing', 3)
        self.leverage_update_delay = delays.get('leverage_update', 2)
        self.position_check_delay = delays.get('position_check', 1)
        
        self.logger.info("[INIT] Risk manager initialized")
    
    def update_leverage(self, symbol: str, leverage: int) -> bool:
        """Обновление плеча для символа"""
        operation_start = time.time()
        
        try:
            self.logger.info(f"[LEVERAGE] Updating {symbol} leverage to {leverage}x")
            
            response = self.exchange.update_leverage(leverage, symbol, is_cross=True)
            
            duration = time.time() - operation_start
            
            if response and response.get('status') == 'ok':
                self.logger.info(f"[LEVERAGE] Successfully updated {symbol} to {leverage}x in {duration:.3f}s")
                return True
            else:
                self.logger.error(f"[LEVERAGE] Failed to update {symbol}: {response}")
                return False
                
        except Exception as e:
            duration = time.time() - operation_start
            self.logger.error(f"[LEVERAGE] Exception updating {symbol} after {duration:.3f}s: {e}")
            return False
    
    def get_current_leverages(self) -> Dict[str, float]:
        """Получение текущих плечей с биржи"""
        operation_start = time.time()
        
        try:
            user_state = self.info.user_state(self.account_address)
            asset_positions = user_state.get('assetPositions', [])
            
            leverages = {}
            
            for pos in asset_positions:
                position_info = pos.get('position', {})
                coin = position_info.get('coin')
                
                if coin:
                    leverage_info = position_info.get('leverage')
                    if leverage_info and isinstance(leverage_info, dict):
                        leverage = float(leverage_info.get('value', 1.0))
                    elif leverage_info:
                        leverage = float(leverage_info)
                    else:
                        leverage = 1.0
                    
                    leverages[coin] = leverage
            
            duration = time.time() - operation_start
            self.logger.debug(f"[LEVERAGE] Retrieved leverages in {duration:.3f}s: {leverages}")
            
            return leverages
            
        except Exception as e:
            duration = time.time() - operation_start
            self.logger.error(f"[LEVERAGE] Failed to get leverages after {duration:.3f}s: {e}")
            return {}
    
    def check_leverage_compliance(self, required_btc: int, required_shorts: int, shorts: List[str]) -> Dict[str, bool]:
        """Проверка соответствия плечей требованиям"""
        operation_start = time.time()
        
        try:
            current_leverages = self.get_current_leverages()
            compliance = {}
            
            # Проверяем BTC
            btc_leverage = current_leverages.get('BTC', 1.0)
            compliance['BTC'] = abs(btc_leverage - required_btc) < 0.01
            
            # Проверяем шорты
            for symbol in shorts:
                symbol_leverage = current_leverages.get(symbol, 1.0)
                compliance[symbol] = abs(symbol_leverage - required_shorts) < 0.01
            
            duration = time.time() - operation_start
            self.logger.debug(f"[LEVERAGE] Compliance check completed in {duration:.3f}s")
            
            # Логируем несоответствия
            non_compliant = [symbol for symbol, compliant in compliance.items() if not compliant]
            if non_compliant:
                self.logger.warning(f"[LEVERAGE] Non-compliant symbols: {non_compliant}")
            
            return compliance
            
        except Exception as e:
            duration = time.time() - operation_start
            self.logger.error(f"[LEVERAGE] Compliance check failed after {duration:.3f}s: {e}")
            return {}
    
    def force_leverage_compliance(self, required_btc: int, required_shorts: int, shorts: List[str]) -> bool:
        """Принудительное приведение плечей в соответствие через полную перенастройку"""
        operation_start = time.time()
        
        try:
            self.logger.info("[LEVERAGE] Starting FULL leverage compliance process")
            
            compliance = self.check_leverage_compliance(required_btc, required_shorts, shorts)
            non_compliant = [symbol for symbol, compliant in compliance.items() if not compliant]
            
            if not non_compliant:
                self.logger.info("[LEVERAGE] All leverages already compliant")
                return True
            
            self.logger.warning(f"[LEVERAGE] Detected non-compliant symbols: {non_compliant}")
            self.logger.info("[LEVERAGE] Starting FULL RESET: Close -> Set Leverage -> Reopen")
            
            # Шаг 1: Сохраняем текущее состояние портфеля для восстановления
            current_state = self._save_portfolio_state(shorts)
            if not current_state:
                self.logger.error("[LEVERAGE] Failed to save portfolio state")
                return False
            
            # Шаг 2: Закрываем ВСЕ позиции
            self.logger.info("[LEVERAGE] Step 1/3: Closing ALL positions")
            if not self._close_all_positions():
                self.logger.error("[LEVERAGE] Failed to close all positions")
                return False
            
            # Шаг 3: Устанавливаем правильные плечи
            self.logger.info("[LEVERAGE] Step 2/3: Setting correct leverages")
            if not self._set_all_leverages(required_btc, required_shorts, shorts):
                self.logger.error("[LEVERAGE] Failed to set leverages")
                return False
            
            # Шаг 4: Восстанавливаем позиции с правильными плечами
            self.logger.info("[LEVERAGE] Step 3/3: Reopening positions with correct leverages")
            if not self._restore_positions(current_state, required_btc, required_shorts):
                self.logger.error("[LEVERAGE] Failed to restore positions")
                return False
            
            duration = time.time() - operation_start
            self.logger.info(f"[LEVERAGE] FULL leverage compliance completed successfully in {duration:.3f}s")
            
            return True
            
        except Exception as e:
            duration = time.time() - operation_start
            self.logger.error(f"[LEVERAGE] FULL leverage compliance failed after {duration:.3f}s: {e}")
            return False
    
    def _save_portfolio_state(self, shorts: List[str]) -> Dict:
        """Сохранение текущего состояния портфеля"""
        try:
            user_state = self.info.user_state(self.account_address)
            asset_positions = user_state.get('assetPositions', [])
            margin_summary = user_state.get('marginSummary', {})
            
            state = {
                'nav': float(margin_summary.get('accountValue', 0.0)),
                'positions': {},
                'total_btc_value': 0.0,
                'total_shorts_value': 0.0
            }
            
            # Получаем цены
            from market_data_provider import HyperliquidMarketDataProvider
            market_data = HyperliquidMarketDataProvider()
            prices = market_data.get_prices(['BTC'] + shorts)
            
            for pos in asset_positions:
                position_info = pos.get('position', {})
                coin = position_info.get('coin')
                size = float(position_info.get('szi', 0.0))
                
                if coin and abs(size) > 1e-8:
                    price = prices.get(coin, 0.0)
                    value = abs(size) * price
                    
                    state['positions'][coin] = {
                        'size': size,
                        'value': value,
                        'price': price
                    }
                    
                    if coin == 'BTC':
                        state['total_btc_value'] += value
                    elif coin in shorts:
                        state['total_shorts_value'] += value
            
            self.logger.info(f"[LEVERAGE] Saved state: NAV=${state['nav']:.2f}, BTC=${state['total_btc_value']:.2f}, Shorts=${state['total_shorts_value']:.2f}")
            return state
            
        except Exception as e:
            self.logger.error(f"[LEVERAGE] Failed to save portfolio state: {e}")
            return {}
    
    def _close_all_positions(self) -> bool:
        """Закрытие всех позиций"""
        try:
            user_state = self.info.user_state(self.account_address)
            asset_positions = user_state.get('assetPositions', [])
            
            positions_to_close = []
            for pos in asset_positions:
                position_info = pos.get('position', {})
                coin = position_info.get('coin')
                size = float(position_info.get('szi', 0.0))
                
                if coin and abs(size) > 1e-8:
                    positions_to_close.append((coin, size))
            
            if not positions_to_close:
                self.logger.info("[LEVERAGE] No positions to close")
                return True
            
            self.logger.info(f"[LEVERAGE] Closing {len(positions_to_close)} positions")
            
            success = True
            for coin, size in positions_to_close:
                try:
                    # Закрываем позицию рыночным ордером
                    is_buy = size < 0  # Если позиция короткая, покупаем для закрытия
                    close_size = abs(size)
                    
                    self.logger.info(f"[LEVERAGE] Closing {coin}: {'BUY' if is_buy else 'SELL'} {close_size:.6f}")
                    
                    # Используем market_close для закрытия позиций
                    response = self.exchange.market_close(coin)
                    
                    if response and response.get('status') == 'ok':
                        self.logger.info(f"[LEVERAGE] Successfully closed {coin} position")
                    else:
                        self.logger.error(f"[LEVERAGE] Failed to close {coin}: {response}")
                        success = False
                        
                except Exception as e:
                    self.logger.error(f"[LEVERAGE] Exception closing {coin}: {e}")
                    success = False
            
            # Ждем обработки ордеров (конфигурируемая задержка)
            delay = getattr(self, 'order_processing_delay', 3)
            time.sleep(delay)
            return success
            
        except Exception as e:
            self.logger.error(f"[LEVERAGE] Failed to close positions: {e}")
            return False
    
    def _set_all_leverages(self, required_btc: int, required_shorts: int, shorts: List[str]) -> bool:
        """Установка всех плечей"""
        try:
            success = True
            
            # Устанавливаем BTC leverage
            if not self.update_leverage('BTC', required_btc):
                success = False
            
            # Устанавливаем leverage для шортов
            for symbol in shorts:
                if not self.update_leverage(symbol, required_shorts):
                    success = False
            
            # Ждем обновления настроек (конфигурируемая задержка)
            delay = getattr(self, 'leverage_update_delay', 2)
            time.sleep(delay)
            return success
            
        except Exception as e:
            self.logger.error(f"[LEVERAGE] Failed to set leverages: {e}")
            return False
    
    def _restore_positions(self, saved_state: Dict, btc_leverage: int, shorts_leverage: int) -> bool:
        """Восстановление позиций с правильными плечами"""
        try:
            # Рассчитываем доступные средства для торговли (с учетом резерва)
            nav = saved_state['nav']
            reserve_percent = 0.05  # 5% резерв
            available_for_trading = nav * (1.0 - reserve_percent)
            
            # Если нет позиций для восстановления, создаем начальные позиции согласно стратегии
            if not saved_state.get('positions') or saved_state.get('total_btc_value', 0) == 0:
                self.logger.info("[LEVERAGE] No positions to restore, creating initial positions based on strategy")
                shorts_symbols = ['ZK', 'STRK']  # Используем стандартные шорты
                return self._create_initial_positions(available_for_trading, btc_leverage, shorts_leverage, shorts_symbols)
            
            # Рассчитываем целевые размеры позиций на основе сохраненного соотношения
            total_btc_value = saved_state['total_btc_value']
            total_shorts_value = saved_state['total_shorts_value']
            total_value = total_btc_value + total_shorts_value
            
            if total_value == 0:
                self.logger.info("[LEVERAGE] No value to restore, creating initial positions")
                shorts_symbols = ['ZK', 'STRK']  # Используем стандартные шорты
                return self._create_initial_positions(available_for_trading, btc_leverage, shorts_leverage, shorts_symbols)
            
            # Восстанавливаем пропорции
            btc_ratio = total_btc_value / total_value
            shorts_ratio = total_shorts_value / total_value
            
            target_btc_value = available_for_trading * btc_ratio
            target_shorts_value = available_for_trading * shorts_ratio
            
            self.logger.info(f"[LEVERAGE] Restoring: BTC=${target_btc_value:.2f}, Shorts=${target_shorts_value:.2f}")
            
            success = True
            
            # Восстанавливаем BTC позицию
            if target_btc_value > 5.0:  # Минимум $5
                if not self._open_position('BTC', target_btc_value, btc_leverage, True):
                    success = False
            
            # Восстанавливаем позиции шортов
            shorts_positions = {k: v for k, v in saved_state['positions'].items() if k != 'BTC'}
            if shorts_positions and target_shorts_value > 5.0:
                shorts_per_symbol = target_shorts_value / len(shorts_positions)
                
                for symbol in shorts_positions.keys():
                    if not self._open_position(symbol, shorts_per_symbol, shorts_leverage, False):
                        success = False
            
            return success
            
        except Exception as e:
            self.logger.error(f"[LEVERAGE] Failed to restore positions: {e}")
            return False
    
    def _open_position(self, symbol: str, target_value: float, leverage: int, is_buy: bool) -> bool:
        """Открытие позиции с заданным размером и плечом"""
        try:
            # Получаем текущую цену
            from market_data_provider import HyperliquidMarketDataProvider
            market_data = HyperliquidMarketDataProvider()
            prices = market_data.get_prices([symbol])
            price = prices.get(symbol, 0.0)
            
            if price == 0:
                self.logger.error(f"[LEVERAGE] No price for {symbol}")
                return False
            
            # Рассчитываем размер позиции
            raw_size = target_value / price
            
            # Валидируем и округляем размер
            is_valid, size, error_msg = self._validate_order_size(symbol, raw_size)
            if not is_valid:
                self.logger.error(f"[LEVERAGE] Size validation failed for {symbol}: {error_msg}")
                return False
            
            self.logger.info(f"[LEVERAGE] Opening {symbol}: {'BUY' if is_buy else 'SELL'} {size:.6f} @ ${price:.4f} (${target_value:.2f})")
            
            # Используем market_open для открытия позиций
            response = self.exchange.market_open(symbol, is_buy=is_buy, sz=size, px=price)
            
            if response and response.get('status') == 'ok':
                self.logger.info(f"[LEVERAGE] Successfully opened {symbol} position")
                return True
            else:
                self.logger.error(f"[LEVERAGE] Failed to open {symbol}: {response}")
                return False
                
        except Exception as e:
            self.logger.error(f"[LEVERAGE] Exception opening {symbol}: {e}")
            return False
    
    def _create_initial_positions(self, available_for_trading: float, btc_leverage: int, shorts_leverage: int, shorts_symbols: List[str]) -> bool:
        """Создание начальных позиций согласно стратегии (ratio_target = 2.0)"""
        try:
            # Согласно стратегии: BTC:Shorts = 2:1 по марже
            # Это означает BTC_margin = 2 * Shorts_margin
            # Если total_margin = BTC_margin + Shorts_margin = 2*Shorts_margin + Shorts_margin = 3*Shorts_margin
            # То Shorts_margin = total_margin / 3, BTC_margin = 2 * total_margin / 3
            
            # Рассчитываем целевые значения маржи
            target_btc_margin = available_for_trading * (2.0 / 3.0)  # 66.67%
            target_shorts_margin = available_for_trading * (1.0 / 3.0)  # 33.33%
            
            self.logger.info(f"[LEVERAGE] Creating initial positions: BTC margin=${target_btc_margin:.2f}, Shorts margin=${target_shorts_margin:.2f}")
            
            success = True
            
            # Открываем BTC позицию (лонг)
            if target_btc_margin > 5.0:  # Минимум $5
                btc_position_value = target_btc_margin * btc_leverage  # Размер позиции = маржа * плечо
                if not self._open_position('BTC', btc_position_value, btc_leverage, True):
                    self.logger.error("[LEVERAGE] Failed to open BTC position")
                    success = False
                else:
                    self.logger.info(f"[LEVERAGE] Opened BTC position: ${btc_position_value:.2f} (margin: ${target_btc_margin:.2f})")
            
            # Открываем позиции шортов (поровну между символами)
            if target_shorts_margin > 5.0:  # Минимум $5
                shorts_margin_per_symbol = target_shorts_margin / len(shorts_symbols)
                shorts_position_value_per_symbol = shorts_margin_per_symbol * shorts_leverage
                
                for symbol in shorts_symbols:
                    if not self._open_position(symbol, shorts_position_value_per_symbol, shorts_leverage, False):
                        self.logger.error(f"[LEVERAGE] Failed to open {symbol} short position")
                        success = False
                    else:
                        self.logger.info(f"[LEVERAGE] Opened {symbol} short: ${shorts_position_value_per_symbol:.2f} (margin: ${shorts_margin_per_symbol:.2f})")
            
            if success:
                self.logger.info("[LEVERAGE] ✅ All initial positions created successfully")
            else:
                self.logger.error("[LEVERAGE] ❌ Some initial positions failed to open")
            
            return success
            
        except Exception as e:
            self.logger.error(f"[LEVERAGE] Failed to create initial positions: {e}")
            return False
    
    def get_position_details_with_leverage(self) -> Dict[str, Dict]:
        """Получение детальной информации о позициях с leverage"""
        try:
            user_state = self.info.user_state(self.account_address)
            asset_positions = user_state.get('assetPositions', [])
            margin_summary = user_state.get('marginSummary', {})
            
            details = {
                'margin_summary': {
                    'account_value': float(margin_summary.get('accountValue', 0.0)),
                    'total_margin_used': float(margin_summary.get('totalMarginUsed', 0.0)),
                    'total_raw_usd': float(margin_summary.get('totalRawUsd', 0.0)),
                    'withdrawable': float(margin_summary.get('withdrawable', 0.0))
                },
                'positions': {}
            }
            
            btc_margin_used = 0.0
            shorts_margin_used = 0.0
            
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
                    
                    details['positions'][coin] = {
                        'size': size,
                        'unrealized_pnl': unrealized_pnl,
                        'margin_used': margin_used,
                        'leverage': leverage
                    }
                    
                    # Суммируем маржу
                    if coin == 'BTC':
                        btc_margin_used += margin_used
                    else:
                        shorts_margin_used += margin_used
            
            details['margin_summary']['btc_margin_used'] = btc_margin_used
            details['margin_summary']['shorts_margin_used'] = shorts_margin_used
            
            return details
            
        except Exception as e:
            self.logger.error(f"[LEVERAGE] Failed to get position details: {e}")
            return {}
    
    def _validate_order_size(self, symbol: str, size: float) -> Tuple[bool, float, str]:
        """Валидация размера ордера согласно требованиям биржи"""
        try:
            asset_params = self.asset_meta.get(symbol)
            if asset_params is None:
                return False, 0.0, f"No meta info for {symbol}"
            
            min_sz = float(asset_params.get('minSz', 10 ** (-int(asset_params.get('szDecimals', 6)))))
            sz_step = float(asset_params.get('szStep', 10 ** (-int(asset_params.get('szDecimals', 6)))))
            sz_decimals = int(asset_params.get('szDecimals', 6))
            
            # Округление размера согласно szStep
            rounded_size = round(round(size / sz_step) * sz_step, sz_decimals)
            
            if rounded_size < min_sz:
                return False, rounded_size, f"Size {rounded_size} < minSz {min_sz}"
            
            self.logger.debug(f"[LEVERAGE] Validated {symbol}: {size:.8f} -> {rounded_size:.8f}")
            return True, rounded_size, ""
            
        except Exception as e:
            return False, 0.0, f"Validation error: {e}" 