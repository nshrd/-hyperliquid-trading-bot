import logging
import datetime
import os
from typing import Optional


class ColoredFormatter(logging.Formatter):
    """Цветной форматтер для консольного вывода"""
    # ANSI цветовые коды
    COLORS = {
        'DEBUG': '\033[36m',     # Голубой
        'INFO': '\033[32m',      # Зеленый
        'WARNING': '\033[33m',   # Желтый
        'ERROR': '\033[31m',     # Красный
        'CRITICAL': '\033[35m',  # Фиолетовый
    }

    # Специальные цвета для разных типов сообщений
    SPECIAL_COLORS = {
        '[POSITIONS]': '\033[94m',      # Ярко-синий
        '[ORDER]': '\033[96m',          # Ярко-голубой
        '[FUNDING]': '\033[93m',        # Ярко-желтый
        '[INIT]': '\033[92m',           # Ярко-зеленый
        '[NAV]': '\033[1;32m',          # Жирный зеленый
        '[LEVERAGE]': '\033[1;33m',     # Жирный желтый
        '[REBALANCE]': '\033[1;36m',    # Жирный голубой
        '[ERROR]': '\033[1;31m',        # Жирный красный
        '[SUCCESS]': '\033[1;32m',      # Жирный зеленый
        '[FAIL]': '\033[1;31m',         # Жирный красный
        'MAIN LOOP': '\033[95m',        # Ярко-фиолетовый
    }

    RESET = '\033[0m'  # Сброс цвета

    def format(self, record):
        # Получаем базовое сообщение
        message = super().format(record)

        # Применяем цвет уровня логирования
        level_color = self.COLORS.get(record.levelname, '')

        # Ищем специальные ключевые слова для дополнительной раскраски
        for keyword, color in self.SPECIAL_COLORS.items():
            if keyword in message:
                message = message.replace(keyword, f"{color}{keyword}{self.RESET}")
                break

        # Применяем основной цвет
        if level_color:
            # Раскрашиваем только уровень и время, сообщение остается с специальными цветами
            parts = message.split(' - ', 2)
            if len(parts) >= 3:
                timestamp, level, msg = parts[0], parts[1], parts[2]
                message = f"{level_color}{timestamp} - {level}{self.RESET} - {msg}"
            else:
                message = f"{level_color}{message}{self.RESET}"

        return message


class TradingFilter(logging.Filter):
    """Фильтр для отбора только важных торговых событий"""

    IMPORTANT_KEYWORDS = [
        # Критические ошибки и проблемы
        'error', 'exception', 'failed', 'fail', 'timeout', 'connection',
        # Торговые операции
        'order', 'position', 'rebalance', 'leverage', 'nav', 'pnl',
        # Состояние системы
        'init', 'start', 'stop', 'shutdown', 'config',
        # API операции
        'api', 'hyperliquid', 'response',
        # Важные изменения
        'update', 'change', 'ratio', 'target', 'actual'
    ]

    def filter(self, record):
        """Фильтрует записи - пропускает только важные"""
        # Всегда пропускаем WARNING и выше
        if record.levelno >= logging.WARNING:
            return True

        # Проверяем наличие важных ключевых слов (без учета регистра)
        message_lower = record.getMessage().lower()
        return any(keyword in message_lower for keyword in self.IMPORTANT_KEYWORDS)


# Глобальная переменная для хранения единого файла сессии
_session_log_file: Optional[str] = None
_session_timestamp: Optional[str] = None


def get_session_log_file() -> str:
    """Получает имя файла для текущей сессии торговли"""
    global _session_log_file, _session_timestamp

    if _session_log_file is None:
        _session_timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        os.makedirs("logs", exist_ok=True)
        _session_log_file = os.path.join("logs", f"trading_session_{_session_timestamp}.log")

        # Записываем заголовок сессии
        with open(_session_log_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write(f"HYPERLIQUID TRADING SESSION STARTED: {datetime.datetime.now()}\n")
            f.write("=" * 80 + "\n")

    return _session_log_file


def setup_unified_logger(name: str, console_level: int = logging.INFO, file_level: int = logging.INFO):
    """
    Настройка единого логгера для всех модулей торгового бота

    Args:
        name: Имя логгера (модуля)
        console_level: Уровень логирования для консоли
        file_level: Уровень логирования для файла

    Returns:
        Настроенный логгер
    """
    # Создаем логгер
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # Логгер принимает все уровни
    logger.propagate = False  # Отключаем передачу в родительские логгеры

    # Очищаем старые обработчики
    logger.handlers = []

    # Получаем единый файл сессии
    session_log_file = get_session_log_file()

    # Обработчик для файла (с фильтрацией важных событий)
    file_handler = logging.FileHandler(session_log_file, encoding='utf-8')
    file_handler.setLevel(file_level)
    file_handler.addFilter(TradingFilter())  # Добавляем фильтр
    file_formatter = logging.Formatter('%(asctime)s [%(name)s] %(levelname)s: %(message)s')
    file_handler.setFormatter(file_formatter)

    # Обработчик для консоли (с цветами, все важные сообщения)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.addFilter(TradingFilter())  # Добавляем тот же фильтр
    console_formatter = ColoredFormatter('%(asctime)s [%(name)s] %(levelname)s: %(message)s')
    console_handler.setFormatter(console_formatter)

    # Добавляем обработчики
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Логируем инициализацию модуля
    logger.info(f"[INIT] Module {name} initialized")

    return logger


def log_session_end():
    """Записывает окончание сессии в лог"""
    if _session_log_file:
        with open(_session_log_file, 'a', encoding='utf-8') as f:
            f.write("\n" + "=" * 80 + "\n")
            f.write(f"TRADING SESSION ENDED: {datetime.datetime.now()}\n")
            f.write("=" * 80 + "\n")

# Для обратной совместимости


def setup_logger(name: str, log_dir: str = "logs", console_level: int = logging.INFO, file_level: int = logging.DEBUG):
    """Обратная совместимость - перенаправляет на новую систему"""
    return setup_unified_logger(name, console_level, file_level)
