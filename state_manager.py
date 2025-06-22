import json
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from logger_config import setup_unified_logger


@dataclass
class NavRecord:
    """Запись NAV"""
    date: str
    nav: float


@dataclass
class CommissionRecord:
    """Запись комиссии"""
    date: str
    symbol: str
    side: str
    size: float
    price: float
    commission: Optional[float] = None
    commission_token: Optional[str] = None
    commission_usd: Optional[float] = None
    oid: Optional[str] = None
    nav_after_commission: float = 0.0


@dataclass
class FundingRecord:
    """Запись фандинга"""
    time: int
    coin: str
    funding: float
    funding_usd: Optional[float] = None
    endTime: int = 0


class StateManager:
    """Менеджер состояния приложения"""

    def __init__(self, state_file: str = 'state.json', config_file: str = 'config.json'):
        self.logger = setup_unified_logger("state_manager")
        self.state_file = state_file
        self.config_file = config_file

        # Загружаем конфигурацию
        self.config = self._load_config()

        # Инициализируем состояние
        self.nav_history: List[NavRecord] = []
        self.positions: Dict[str, float] = {}
        self.funding_history: Dict[str, List[float]] = {}
        self.rebalance_events: List[Dict[str, Any]] = []
        self.commission_history: List[CommissionRecord] = []
        self.funding_paid_history: List[FundingRecord] = []

        # Загружаем существующее состояние
        self.load_state()

    def _load_config(self) -> dict:
        """Загрузка конфигурации"""
        try:
            with open(self.config_file) as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            raise

    def load_state(self) -> bool:
        """Загрузка состояния из файла"""
        try:
            with open(self.state_file) as f:
                state = json.load(f)

            # Загружаем NAV историю
            self.nav_history = [
                NavRecord(date=record['date'], nav=record['nav'])
                for record in state.get('nav_history', [])
            ]

            # Загружаем позиции
            self.positions = state.get('positions', {})
            if not self.positions:
                # Инициализируем пустые позиции
                symbols = ['BTC'] + self.config.get('shorts', [])
                self.positions = {s: 0.0 for s in symbols}

            # Загружаем историю фандинга
            self.funding_history = state.get('funding_history', {})
            if not self.funding_history:
                symbols = ['BTC'] + self.config.get('shorts', [])
                self.funding_history = {s: [] for s in symbols}

            # Загружаем события ребалансировки
            self.rebalance_events = state.get('rebalance_events', [])

            # Загружаем историю комиссий
            commission_data = state.get('commission_history', [])
            self.commission_history = []
            for record in commission_data:
                try:
                    # Добавляем отсутствующие поля для обратной совместимости
                    if 'commission_usd' not in record:
                        record['commission_usd'] = None
                    if 'nav_after_commission' not in record:
                        record['nav_after_commission'] = 0.0
                    if 'commission' not in record:
                        record['commission'] = None
                    if 'commission_token' not in record:
                        record['commission_token'] = None
                    if 'oid' not in record:
                        record['oid'] = None

                    self.commission_history.append(CommissionRecord(**record))
                except Exception as e:
                    self.logger.warning(f"Failed to load commission record: {e}")
                    continue

            # Загружаем историю фандинга
            funding_data = state.get('funding_paid_history', [])
            self.funding_paid_history = []
            for record in funding_data:
                try:
                    # Добавляем отсутствующие поля для обратной совместимости
                    if 'funding_usd' not in record:
                        record['funding_usd'] = None
                    if 'endTime' not in record:
                        record['endTime'] = record.get('time', 0)

                    self.funding_paid_history.append(FundingRecord(**record))
                except Exception as e:
                    self.logger.warning(f"Failed to load funding record: {e}")
                    continue

            self.logger.info("State loaded successfully")
            return True

        except FileNotFoundError:
            self.logger.info("State file not found, initializing new state")
            self._initialize_empty_state()
            return False
        except Exception as e:
            self.logger.error(f"Failed to load state: {e}")
            self._initialize_empty_state()
            return False

    def _initialize_empty_state(self):
        """Инициализация пустого состояния"""
        symbols = ['BTC'] + self.config.get('shorts', [])
        self.nav_history = []
        self.positions = {s: 0.0 for s in symbols}
        self.funding_history = {s: [] for s in symbols}
        self.rebalance_events = []
        self.commission_history = []
        self.funding_paid_history = []

    def save_state(self) -> bool:
        """Сохранение состояния в файл"""
        try:
            state = {
                'nav_history': [asdict(record) for record in self.nav_history],
                'positions': self.positions,
                'funding_history': self.funding_history,
                'rebalance_events': self.rebalance_events,
                'commission_history': [asdict(record) for record in self.commission_history],
                'funding_paid_history': [asdict(record) for record in self.funding_paid_history]
            }

            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)

            self.logger.debug("State saved successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to save state: {e}")
            return False

    def add_nav_record(self, nav: float) -> None:
        """Добавление записи NAV"""
        record = NavRecord(
            date=time.strftime('%Y-%m-%d %H:%M:%S'),
            nav=nav
        )
        self.nav_history.append(record)

    def update_positions(self, new_positions: Dict[str, float]) -> None:
        """Обновление позиций"""
        self.positions.update(new_positions)

    def add_funding_rates(self, funding_rates: Dict[str, float]) -> None:
        """Добавление ставок фандинга"""
        for symbol, rate in funding_rates.items():
            if symbol in self.funding_history:
                self.funding_history[symbol].append(rate)

    def add_commission_record(self, symbol: str, side: str, size: float, price: float,
                              commission: Optional[float] = None, commission_token: Optional[str] = None,
                              commission_usd: Optional[float] = None, oid: Optional[str] = None,
                              nav_after_commission: float = 0.0) -> None:
        """Добавление записи комиссии"""
        record = CommissionRecord(
            date=time.strftime('%Y-%m-%d %H:%M:%S'),
            symbol=symbol,
            side=side,
            size=size,
            price=price,
            commission=commission,
            commission_token=commission_token,
            commission_usd=commission_usd,
            oid=oid,
            nav_after_commission=nav_after_commission
        )
        self.commission_history.append(record)

    def add_funding_records(self, records: List[dict]) -> None:
        """Добавление записей фандинга"""
        for record in records:
            funding_record = FundingRecord(
                time=record.get('time', 0),
                coin=record.get('coin', ''),
                funding=record.get('funding', 0.0),
                funding_usd=record.get('funding_usd'),
                endTime=record.get('endTime', 0)
            )
            self.funding_paid_history.append(funding_record)

    def get_last_nav(self) -> float:
        """Получение последнего NAV"""
        return self.nav_history[-1].nav if self.nav_history else self.config.get('start_nav', 100.0)

    def get_open_positions(self) -> Dict[str, float]:
        """Получение открытых позиций (с ненулевыми значениями)"""
        return {k: v for k, v in self.positions.items() if abs(v) > 1e-8}

    def get_last_funding_time(self) -> int:
        """Получение времени последней записи фандинга"""
        if not self.funding_paid_history:
            return 0
        return max([rec.endTime for rec in self.funding_paid_history])

    def get_total_commission_usd(self) -> float:
        """Получение общей суммы комиссий в USD"""
        total = 0.0
        for record in self.commission_history:
            if record.commission_usd:
                total += record.commission_usd
        return total

    def get_total_funding_usd(self) -> float:
        """Получение общей суммы фандинга в USD"""
        total = 0.0
        for record in self.funding_paid_history:
            if record.funding_usd:
                total += record.funding_usd
        return total

    def get_summary(self) -> Dict[str, Any]:
        """Получение сводки состояния"""
        return {
            'current_nav': self.get_last_nav(),
            'open_positions': self.get_open_positions(),
            'total_records': len(self.nav_history),
            'total_commission_usd': self.get_total_commission_usd(),
            'total_funding_usd': self.get_total_funding_usd(),
            'last_update': self.nav_history[-1].date if self.nav_history else 'Never'
        }
