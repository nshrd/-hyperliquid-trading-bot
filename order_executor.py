"""
Компонент для исполнения ордеров на Hyperliquid
Реализует интерфейс IOrderExecutor
"""

import time
from typing import Dict, Tuple
from hyperliquid.exchange import Exchange
from hyperliquid.utils.constants import MAINNET_API_URL
from eth_account import Account
import traceback
from logger_config import setup_unified_logger
from interfaces import IOrderExecutor, OrderResult
from exceptions import OrderExecutionError, InvalidOrderSizeError, APIError


class HyperliquidOrderExecutor(IOrderExecutor):
    """Исполнитель ордеров для Hyperliquid"""

    def __init__(self, secret_key: str, account_address: str, asset_meta: Dict[str, dict]):
        self.logger = setup_unified_logger("order_executor")
        self.wallet = Account.from_key(secret_key)
        self.account_address = account_address
        self.exchange = Exchange(self.wallet, base_url=MAINNET_API_URL, account_address=account_address)
        self.asset_meta = asset_meta

        self.logger.info("[INIT] Order executor initialized")

    def place_market_order(self, symbol: str, is_buy: bool, size: float, price: float) -> OrderResult:
        """Размещение рыночного ордера"""
        operation_start = time.time()
        side = "BUY" if is_buy else "SELL"

        try:
            # Валидация размера
            is_valid, validated_size, error_msg = self.validate_order_size(symbol, size)
            if not is_valid:
                self.logger.warning(f"[ORDER] Validation failed for {symbol}: {error_msg}")
                return OrderResult(
                    success=False,
                    error_message=f"Order validation failed: {error_msg}"
                )

            # Размещение ордера
            self.logger.info(f"[ORDER] Placing {side} {validated_size} {symbol} @ ${price:.4f}")

            order_resp = self.exchange.market_open(symbol, is_buy=is_buy, sz=validated_size, px=price)

            # Парсинг ответа
            if order_resp and order_resp.get('status') == 'ok':
                statuses = order_resp.get('response', {}).get('data', {}).get('statuses', [])
                if statuses:
                    status = statuses[0]
                    if status.get('type') == 'success':
                        # Успешное размещение
                        order_id = None
                        if 'resting' in status:
                            order_id = status['resting'].get('oid')

                        duration = time.time() - operation_start
                        self.logger.info(f"[ORDER] SUCCESS: {side} {validated_size} {symbol} in {duration:.3f}s")

                        return OrderResult(
                            success=True,
                            order_id=order_id,
                            filled_size=validated_size,
                            avg_price=price
                        )
                    else:
                        error_msg = status.get('msg', 'Unknown error')
                        self.logger.error(f"[ORDER] FAILED: {error_msg}")
                        self.logger.error(f"[ORDER] Full status: {status}")
                        return OrderResult(
                            success=False,
                            error_message=error_msg
                        )
                else:
                    self.logger.error(f"[ORDER] No statuses in response: {order_resp}")
                    return OrderResult(
                        success=False,
                        error_message="No statuses in response"
                    )

            # Неожиданный ответ
            self.logger.error(f"[ORDER] Unexpected response: {order_resp}")
            return OrderResult(
                success=False,
                error_message=f"Unexpected response: {order_resp}"
            )

        except Exception as e:
            duration = time.time() - operation_start
            self.logger.error(f"[ORDER] Exception after {duration:.3f}s: {e}")
            self.logger.error(traceback.format_exc())
            return OrderResult(
                success=False,
                error_message=str(e)
            )

    def close_position(self, symbol: str) -> OrderResult:
        """Закрытие позиции"""
        operation_start = time.time()

        try:
            self.logger.info(f"[ORDER] Closing position for {symbol}")

            resp = self.exchange.market_close(symbol)

            if resp and resp.get('status') == 'ok':
                duration = time.time() - operation_start
                self.logger.info(f"[ORDER] Position closed for {symbol} in {duration:.3f}s")

                return OrderResult(
                    success=True,
                    order_id=None  # Market close не возвращает order ID
                )
            else:
                error_msg = f"Close failed: {resp}"
                self.logger.error(f"[ORDER] {error_msg}")
                return OrderResult(
                    success=False,
                    error_message=error_msg
                )

        except Exception as e:
            duration = time.time() - operation_start
            self.logger.error(f"[ORDER] Close exception after {duration:.3f}s: {e}")
            return OrderResult(
                success=False,
                error_message=str(e)
            )

    def validate_order_size(self, symbol: str, size: float) -> Tuple[bool, float, str]:
        """Валидация размера ордера"""
        try:
            asset_params = self.asset_meta.get(symbol)
            if asset_params is None:
                return False, 0.0, f"No meta info for {symbol}"

            min_sz = float(asset_params.get('minSz', 10 ** (-int(asset_params.get('szDecimals', 6)))))
            sz_step = float(asset_params.get('szStep', 10 ** (-int(asset_params.get('szDecimals', 6)))))
            sz_decimals = int(asset_params.get('szDecimals', 6))

            # Округление размера
            rounded_size = round(round(size / sz_step) * sz_step, sz_decimals)

            if rounded_size < min_sz:
                return False, rounded_size, f"Size {rounded_size} < minSz {min_sz}"

            self.logger.debug(f"[ORDER] Validated {symbol}: {size} -> {rounded_size}")
            return True, rounded_size, ""

        except Exception as e:
            return False, 0.0, f"Validation error: {e}"

    def close_all_positions(self, positions: Dict[str, float]) -> Dict[str, OrderResult]:
        """Закрытие всех позиций"""
        results = {}

        for symbol, size in positions.items():
            if abs(size) > 1e-8:
                result = self.close_position(symbol)
                results[symbol] = result

                if result.success:
                    self.logger.info(f"[ORDER] Closed {symbol} position")
                else:
                    self.logger.error(f"[ORDER] Failed to close {symbol}: {result.error_message}")

        return results
