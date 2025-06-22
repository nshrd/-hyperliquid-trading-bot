import json
import matplotlib.pyplot as plt
from io import BytesIO
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
import asyncio
import logging
import datetime
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils.constants import MAINNET_API_URL
from eth_account import Account
import subprocess

# Загрузка конфигурации
try:
    with open('config.json') as f:
        config = json.load(f)
    TELEGRAM_TOKEN = config.get('telegram_token')
    TELEGRAM_CHAT_ID = config.get('telegram_chat_id')
    account_address = config.get('account_address')
    secret_key = config.get('secret_key')

    if not all([TELEGRAM_TOKEN, account_address, secret_key]):
        raise ValueError("Missing required config fields for Telegram bot")
except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
    print(f"❌ Config error: {e}")
    exit(1)
wallet = Account.from_key(secret_key)

# Инициализация Hyperliquid SDK
info = Info(MAINNET_API_URL, skip_ws=True)
exchange = Exchange(wallet, base_url=MAINNET_API_URL, account_address=account_address)

trader_process = None


def is_authorized(message: Message) -> bool:
    """Проверка авторизации пользователя"""
    if not TELEGRAM_CHAT_ID:
        return True  # Если chat_id не указан, разрешаем всем
    
    return str(message.chat.id) == str(TELEGRAM_CHAT_ID)


async def unauthorized_handler(message: Message):
    """Обработчик для неавторизованных пользователей"""
    await message.answer("❌ У вас нет доступа к этому боту.")
    return


def load_state():
    with open('state.json') as f:
        return json.load(f)


def save_state(state, path='state.json'):
    with open(path, 'w') as f:
        json.dump(state, f, indent=2)


async def status(message: Message):
    if not is_authorized(message):
        await unauthorized_handler(message)
        return
        
    state = load_state()
    nav = state['nav_history'][-1]['nav'] if state['nav_history'] else 'N/A'
    positions = state['positions']
    msg = f"NAV: {nav}\nПозиции: {positions}"
    await message.answer(msg)


async def plot(message: Message):
    state = load_state()
    nav_hist = state['nav_history']
    if not nav_hist:
        await message.answer('Нет данных для графика.')
        return
    dates = [x['date'] for x in nav_hist]
    navs = [x['nav'] for x in nav_hist]
    plt.figure(figsize=(10, 5))
    plt.plot(dates, navs, label='NAV')
    plt.title('NAV History')
    plt.xlabel('Date')
    plt.ylabel('NAV')
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    buf = BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    await message.answer_photo(photo=buf)


async def rebalance(message: Message):
    await message.answer('Ручная ребалансировка инициирована (заглушка).')


async def closeall(message: Message):
    try:
        user_state = info.user_state(account_address)
        positions = user_state.get('assetPositions', [])
        closed = []
        for pos in positions:
            item = pos['position']
            coin = item['coin']
            szi = float(item['szi'])
            if abs(szi) > 1e-8:
                resp = exchange.market_close(coin)
                closed.append(f"{coin}: {szi} -> close resp: {resp.get('status','?')}")
        if closed:
            await message.answer('Закрыты позиции:\n' + '\n'.join(closed))
        else:
            await message.answer('Нет открытых позиций для закрытия.')
    except Exception as e:
        await message.answer(f'Ошибка при закрытии позиций: {e}')


async def starttrader(message: Message):
    global trader_process
    if trader_process is not None and trader_process.poll() is None:
        await message.answer("Трейдер уже запущен.")
        return
    try:
        trader_process = subprocess.Popen(['python3', 'main.py'])
        await message.answer(f"Трейдер запущен! PID: {trader_process.pid}")
    except Exception as e:
        await message.answer(f"Ошибка запуска трейдера: {e}")


async def help_command(message: Message):
    help_text = (
        "Доступные команды:\n"
        "/status — показать NAV и текущие позиции\n"
        "/plot — график NAV\n"
        "/rebalance — ручная ребалансировка (заглушка)\n"
        "/closeall — закрыть все открытые позиции\n"
        "/starttrader — запустить торгового бота\n"
        "/help — показать это сообщение\n"
        "/myid — узнать свой chat id"
    )
    await message.answer(help_text)


async def myid(message: Message):
    await message.answer(f"Ваш chat id: {message.chat.id}")


async def echo(message: Message):
    await message.answer(f"Получено: {message.text}")


async def main():
    from logger_config import setup_unified_logger

    logger = setup_unified_logger("telegram_bot")

    logger.info("Бот запускается...")
    bot = Bot(
        token=TELEGRAM_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    dp.message.register(status, Command('status'))
    dp.message.register(plot, Command('plot'))
    dp.message.register(rebalance, Command('rebalance'))
    dp.message.register(closeall, Command('closeall'))
    dp.message.register(help_command, Command('help'))
    dp.message.register(myid, Command('myid'))
    dp.message.register(starttrader, Command('starttrader'))
    dp.message.register(echo)
    logger.info("Старт polling...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
