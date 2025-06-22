import json
from typing import Dict, List, Any
from logger_config import setup_unified_logger
from config_validator import ConfigValidator, ConfigValidationError


class ConfigManager:
    """Менеджер конфигурации приложения"""

    def __init__(self, config_path: str = 'config.json'):
        self.logger = setup_unified_logger("config_manager")
        self.config_path = config_path
        self.validator = ConfigValidator()
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Загрузка конфигурации из файла"""
        try:
            with open(self.config_path) as f:
                config = json.load(f)
            self.logger.info(f"Configuration loaded from {self.config_path}")

            # Валидируем конфигурацию
            self.validator.validate_and_raise(config)

            return config
        except ConfigValidationError:
            raise
        except FileNotFoundError:
            self.logger.error(f"Configuration file not found: {self.config_path}")
            raise
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in configuration file: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Failed to load configuration from {self.config_path}: {e}")
            raise

    def save_config(self) -> bool:
        """Сохранение конфигурации в файл"""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            self.logger.info(f"Configuration saved to {self.config_path}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to save configuration: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """Получение значения из конфигурации"""
        return self.config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Установка значения в конфигурации"""
        self.config[key] = value

    @property
    def account_address(self) -> str:
        """Адрес аккаунта"""
        return self.config['account_address']

    @property
    def secret_key(self) -> str:
        """Секретный ключ"""
        return self.config['secret_key']

    @property
    def commission_pct(self) -> float:
        """Процент комиссии"""
        return self.config.get('commission_pct', 0.0004)

    @property
    def shorts(self) -> List[str]:
        """Список активов для коротких позиций"""
        return self.config.get('shorts', [])

    @property
    def all_symbols(self) -> List[str]:
        """Все торгуемые символы (BTC + shorts)"""
        return ['BTC'] + self.shorts

    @property
    def start_nav(self) -> float:
        """Начальный NAV для справки"""
        return self.config.get('start_nav', 100.0)

    @property
    def rebalance_threshold(self) -> float:
        """Порог ребалансировки (процентное отклонение от target)"""
        return self.config.get('rebalance_threshold', 0.02)

    @property
    def ratio_low(self) -> float:
        """Нижняя граница ratio для ребалансировки"""
        return self.config.get('ratio_low', 1.8)

    @property
    def ratio_high(self) -> float:
        """Верхняя граница ratio для ребалансировки"""
        return self.config.get('ratio_high', 2.2)

    @property
    def max_leverage(self) -> int:
        """Максимальное плечо"""
        return self.config.get('max_leverage', 5)

    @property
    def leverage_btc(self) -> int:
        """Плечо для BTC"""
        return self.config.get('leverage_btc', 3)

    @property
    def leverage_shorts(self) -> int:
        """Плечо для шортов"""
        return self.config.get('leverage_shorts', 3)

    @property
    def reserve_usd_percent(self) -> float:
        """Процент резерва в USD"""
        return self.config.get('reserve_usd_percent', 0.05)

    @property
    def ratio_target(self) -> float:
        """Целевое соотношение BTC к шортам"""
        return self.config.get('ratio_tgt', 2.0)

    def validate_config(self) -> bool:
        """Валидация конфигурации (использует новый валидатор)"""
        is_valid, errors = self.validator.validate_config(self.config)
        return is_valid
