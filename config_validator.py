"""
Модуль валидации конфигурации
Проверяет обязательные поля и корректность значений в config.json
"""

from typing import Dict, Any, List, Tuple
from logger_config import setup_unified_logger


class ConfigValidationError(Exception):
    """Исключение для ошибок валидации конфигурации"""
    pass


class ConfigValidator:
    """Валидатор конфигурации"""

    def __init__(self):
        self.logger = setup_unified_logger("config_validator")

    def validate_config(self, config: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Валидация конфигурации

        Returns:
            Tuple[bool, List[str]]: (is_valid, error_messages)
        """
        errors = []

        # Проверяем обязательные поля
        required_fields = [
            'account_address',
            'secret_key',
            'start_nav',
            'gross',
            'ratio_tgt',
            'ratio_low',
            'ratio_high',
            'leverage_btc',
            'leverage_shorts',
            'shorts'
        ]

        for field in required_fields:
            if field not in config:
                errors.append(f"Missing required field: {field}")

        # Проверяем типы и значения
        if 'account_address' in config:
            if not isinstance(config['account_address'], str) or not config['account_address'].startswith('0x'):
                errors.append("account_address must be a valid Ethereum address starting with 0x")

        if 'secret_key' in config:
            if not isinstance(config['secret_key'], str) or not config['secret_key'].startswith('0x'):
                errors.append("secret_key must be a valid private key starting with 0x")

        # Проверяем числовые значения
        numeric_fields = {
            'start_nav': (float, 1.0, 1000000.0),
            'gross': (float, 1.0, 10.0),
            'ratio_tgt': (float, 0.1, 10.0),
            'ratio_low': (float, 0.1, 10.0),
            'ratio_high': (float, 0.1, 10.0),
            'leverage_btc': (int, 1, 50),
            'leverage_shorts': (int, 1, 50)
        }

        for field, (expected_type, min_val, max_val) in numeric_fields.items():
            if field in config:
                try:
                    value = expected_type(config[field])
                    if not (min_val <= value <= max_val):
                        errors.append(f"{field} must be between {min_val} and {max_val}")
                except (ValueError, TypeError):
                    errors.append(f"{field} must be a valid {expected_type.__name__}")

        # Проверяем логические значения
        boolean_fields = ['rebalance_enabled']
        for field in boolean_fields:
            if field in config and not isinstance(config[field], bool):
                errors.append(f"{field} must be a boolean value")

        # Проверяем массивы
        if 'shorts' in config:
            if not isinstance(config['shorts'], list) or len(config['shorts']) == 0:
                errors.append("shorts must be a non-empty list")
            else:
                for symbol in config['shorts']:
                    if not isinstance(symbol, str) or len(symbol) == 0:
                        errors.append(f"Invalid symbol in shorts: {symbol}")

        # Проверяем соотношения
        if all(field in config for field in ['ratio_low', 'ratio_tgt', 'ratio_high']):
            if not (config['ratio_low'] <= config['ratio_tgt'] <= config['ratio_high']):
                errors.append("ratio_low <= ratio_tgt <= ratio_high constraint violated")

        # Проверяем опциональные поля
        optional_fields = {
            'reserve_usd_percent': (float, 0.0, 0.5),
            'stop_loss_pct': (float, 0.01, 0.5),
            'min_shorts': (int, 1, 10)
        }

        for field, (expected_type, min_val, max_val) in optional_fields.items():
            if field in config:
                try:
                    value = expected_type(config[field])
                    if not (min_val <= value <= max_val):
                        errors.append(f"{field} must be between {min_val} and {max_val}")
                except (ValueError, TypeError):
                    errors.append(f"{field} must be a valid {expected_type.__name__}")

        # Проверяем API delays
        if 'api_delays' in config:
            if not isinstance(config['api_delays'], dict):
                errors.append("api_delays must be an object")
            else:
                delay_fields = ['order_processing', 'leverage_update', 'position_check']
                for delay_field in delay_fields:
                    if delay_field in config['api_delays']:
                        try:
                            delay_value = int(config['api_delays'][delay_field])
                            if not (1 <= delay_value <= 30):
                                errors.append(f"api_delays.{delay_field} must be between 1 and 30 seconds")
                        except (ValueError, TypeError):
                            errors.append(f"api_delays.{delay_field} must be a valid integer")

        # Проверяем Telegram настройки (опционально)
        if 'telegram_token' in config:
            if not isinstance(config['telegram_token'], str) or ':' not in config['telegram_token']:
                errors.append("telegram_token must be a valid Telegram bot token")

        if 'telegram_chat_id' in config:
            try:
                int(config['telegram_chat_id'])
            except (ValueError, TypeError):
                errors.append("telegram_chat_id must be a valid integer")

        is_valid = len(errors) == 0

        if is_valid:
            self.logger.info("Configuration validation passed")
        else:
            self.logger.error(f"Configuration validation failed with {len(errors)} errors")
            for error in errors:
                self.logger.error(f"  - {error}")

        return is_valid, errors

    def validate_and_raise(self, config: Dict[str, Any]) -> None:
        """
        Валидация конфигурации с выбрасыванием исключения при ошибке
        """
        is_valid, errors = self.validate_config(config)
        if not is_valid:
            error_message = "Configuration validation failed:\n" + "\n".join(f"  - {error}" for error in errors)
            raise ConfigValidationError(error_message)
