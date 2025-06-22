#!/usr/bin/env python3
"""
Главная точка входа для Hyperliquid трейдера
"""

import sys
import argparse
import signal
import time
import logging
from typing import TYPE_CHECKING
from trader import HyperliquidTrader
from logger_config import log_session_end

if TYPE_CHECKING:
    from trader import HyperliquidTrader


def log_session_end() -> None:
    """Логирование завершения сессии"""
    current_time = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n📝 Session ended at {current_time}")


def show_menu() -> None:
    """Отображение главного меню"""
    print("\n" + "=" * 50)
    print("🤖 HYPERLIQUID TRADING BOT")
    print("=" * 50)
    print("1. 🚀 Запустить трейдера (основной цикл)")
    print("2. ⚙️  Управление плечом (leverage)")
    print("3. 🛑 Закрыть все позиции")
    print("4. ⚖️  Принудительная ребалансировка")
    print("5. 📊 Показать статус портфеля")
    print("0. 👋 Выход")
    print("=" * 50)


def handle_leverage_menu(trader: 'HyperliquidTrader') -> None:
    """Обработка меню управления плечом"""
    while True:
        print("\n" + "=" * 40)
        print("⚙️  УПРАВЛЕНИЕ ПЛЕЧОМ")
        print("=" * 40)
        print("1. 🔍 Проверить текущие настройки leverage")
        print("2. 🔄 ПОЛНЫЙ СБРОС (закрыть все + установить leverage + восстановить)")
        print("0. ⬅️  Назад в главное меню")
        print("=" * 40)

        choice = input("\nВаш выбор (0-2): ").strip()

        if choice == "0":
            break

        elif choice == "1":
            try:
                # Получаем статус leverage compliance
                status = trader.get_portfolio_status()
                current_leverages = status.get('current_leverages', {})
                compliance = status.get('leverage_compliance', {})

                print(f"\n🔍 Текущие настройки leverage:")
                print(f"📋 Конфигурация: BTC={trader.config_manager.leverage_btc}x, "
                      f"Shorts={trader.config_manager.leverage_shorts}x")

                if current_leverages:
                    print(f"\n📊 Текущие leverage на бирже:")
                    for symbol, leverage in current_leverages.items():
                        expected = (trader.config_manager.leverage_btc if symbol == 'BTC'
                                    else trader.config_manager.leverage_shorts)
                        is_compliant = compliance.get(symbol, False)
                        status_icon = "✅" if is_compliant else "❌"
                        print(f"  {status_icon} {symbol}: {leverage:.1f}x (ожидается: {expected}x)")

                    if all(compliance.values()):
                        print("\n✅ Все leverage настроены корректно!")
                    else:
                        non_compliant = [symbol for symbol, compliant in compliance.items() if not compliant]
                        print(f"\n⚠️  Проблемы с leverage: {non_compliant}")
                        print("   💡 Используйте опцию 2 для ПОЛНОГО СБРОСА")
                else:
                    print("\n❌ Не удалось получить информацию о leverage")

            except Exception as e:
                print(f"\n❌ Ошибка при проверке leverage: {e}")

        elif choice == "2":
            print("\n⚠️  ПОЛНЫЙ СБРОС LEVERAGE")
            print("Это действие:")
            print("1️⃣  Закроет ВСЕ открытые позиции")
            print("2️⃣  Установит корректные leverage для всех символов")
            print("3️⃣  Восстановит позиции согласно стратегии")
            print("\n🚨 ВНИМАНИЕ: Это может повлиять на ваш PnL!")

            confirm = input("\nВы уверены? Введите 'RESET' для подтверждения: ").strip()

            if confirm == 'RESET':
                print("\n🔄 Выполняется ПОЛНЫЙ СБРОС...")
                try:
                    success = trader.risk_manager.force_leverage_compliance(
                        trader.config_manager.leverage_btc,
                        trader.config_manager.leverage_shorts,
                        trader.config_manager.shorts
                    )

                    if success:
                        print("✅ ПОЛНЫЙ СБРОС выполнен успешно!")
                        print("✅ Все leverage установлены корректно")
                        print("✅ Позиции восстановлены согласно стратегии")
                    else:
                        print("❌ ПОЛНЫЙ СБРОС завершился с ошибками!")
                        print("❌ Проверьте логи для подробной информации")

                except Exception as e:
                    print(f"❌ Ошибка при ПОЛНОМ СБРОСЕ: {e}")
            else:
                print("❌ Операция отменена")

        else:
            print("❌ Некорректный выбор! Попробуйте снова.")

        input("\nНажмите Enter для продолжения...")


def show_portfolio_status(trader: 'HyperliquidTrader') -> None:
    """Отображение статуса портфеля"""
    try:
        print("\n📊 СТАТУС ПОРТФЕЛЯ")
        print("=" * 50)

        status = trader.get_portfolio_status()

        nav = status.get('nav', 0)
        btc_value = status.get('btc_value_usd', 0)
        shorts_value = status.get('shorts_value_usd', 0)
        current_ratio = status.get('position_ratio', 0)
        target_ratio = status.get('target_ratio', 2.0)
        open_positions = status.get('open_positions', {})
        position_details = status.get('position_details', {})
        margin_summary = status.get('margin_summary', {})

        print(f"💰 NAV: ${nav:.2f}")

        # Показываем резерв если он есть
        reserve_percent = getattr(trader.config_manager, 'reserve_usd_percent', 0.05)
        reserve_amount = nav * reserve_percent
        nav_for_trading = nav - reserve_amount

        if reserve_amount > 0:
            print(f"🏦 Reserve ({reserve_percent:.1%}): ${reserve_amount:.2f}")
            print(f"💹 NAV for Trading: ${nav_for_trading:.2f}")

        print("\n📊 Position Analysis:")
        print(f"📈 BTC Value: ${btc_value:.2f}")
        print(f"📉 Shorts Value: ${shorts_value:.2f}")
        print(f"⚖️  Position Ratio (by margin): {current_ratio:.2f} (Target: {target_ratio:.2f})")

        if current_ratio and target_ratio and target_ratio > 0:
            ratio_deviation_pct = abs(current_ratio - target_ratio) / target_ratio * 100
            print(f"📈 Position Ratio Deviation: {ratio_deviation_pct:.1f}%")

        if margin_summary:
            btc_margin_used = margin_summary.get('btc_margin_used', 0)
            shorts_margin_used = margin_summary.get('shorts_margin_used', 0)
            total_margin_used = margin_summary.get('total_margin_used', 0)

            print("\n💳 Margin Analysis:")
            if total_margin_used > 0:
                print(f"📊 Total Margin Used: ${total_margin_used:.2f}")
            if btc_margin_used > 0:
                print(f"📈 BTC Margin: ${btc_margin_used:.2f}")
            if shorts_margin_used > 0:
                print(f"📉 Shorts Margin: ${shorts_margin_used:.2f}")

        print("\n⚙️ Leverage Settings:")
        print(f"📈 BTC Config Leverage: {trader.config_manager.leverage_btc}x")
        print(f"📉 Shorts Config Leverage: {trader.config_manager.leverage_shorts}x")

        try:
            current_leverages = status.get('current_leverages', {})
            compliance = status.get('leverage_compliance', {})

            if current_leverages:
                print("\n🔍 Current Leverages on Exchange:")
                for symbol, leverage in current_leverages.items():
                    expected = (trader.config_manager.leverage_btc if symbol == 'BTC'
                                else trader.config_manager.leverage_shorts)
                    is_compliant = compliance.get(symbol, False)
                    status_icon = "✅" if is_compliant else "❌"
                    print(f"{status_icon} {symbol}: {leverage:.1f}x (expected: {expected}x)")

                if all(compliance.values()):
                    print("\n✅ All leverages are compliant with config")
                else:
                    non_compliant = [symbol for symbol, compliant in compliance.items() if not compliant]
                    print(f"\n⚠️  Leverage compliance issues: {non_compliant}")
                    print("   🔄 Use option 2 to perform FULL RESET")

        except Exception as e:
            print(f"\n❌ Error checking leverage compliance: {e}")

        if open_positions:
            print("\n📍 Open Positions:")
            for symbol in open_positions.keys():
                details = position_details.get(symbol, {})
                size = details.get('size', 0)
                unrealized_pnl = details.get('unrealized_pnl', 0)
                margin_used = details.get('margin_used', 0)

                side = "LONG" if size > 0 else "SHORT"
                pnl_sign = "+" if unrealized_pnl >= 0 else ""

                print(f"  {symbol} {side}: {pnl_sign}${unrealized_pnl:.2f} PnL (Margin: ${margin_used:.2f})")
        else:
            print("\n✅ No open positions")

    except Exception as e:
        print(f"❌ Ошибка при получении статуса портфеля: {e}")


def main() -> None:
    """Главная функция с интерактивным меню"""
    parser = argparse.ArgumentParser(description='Hyperliquid Trading Bot')
    parser.add_argument('--config', '-c', default='config.json', help='Путь к файлу конфигурации')
    parser.add_argument('--status', action='store_true', help='Показать статус портфеля и выйти')
    parser.add_argument('--close', action='store_true', help='Закрыть все позиции и выйти')
    parser.add_argument('--verbose', '-v', action='store_true', help='Подробный вывод')
    args = parser.parse_args()

    try:
        print("🚀 Initializing Hyperliquid Trader...")
        trader = HyperliquidTrader(config_path=args.config)

        # Если переданы аргументы командной строки
        if args.status:
            show_portfolio_status(trader)
            return

        if args.close:
            print("\n⚠️  EMERGENCY: Closing all positions...")
            status = trader.get_portfolio_status()
            open_positions = status.get('open_positions', {})

            if not open_positions:
                print("✅ No positions to close")
                return

            print(f"📍 Positions to close: {list(open_positions.keys())}")
            confirm = input("Are you sure you want to close ALL positions? (yes/no): ")

            if confirm.lower() == 'yes':
                success = trader.close_all_positions()
                if success:
                    print("✅ All positions closed successfully")
                else:
                    print("❌ Failed to close some positions")
            else:
                print("❌ Operation cancelled")
            return

        # Интерактивное меню
        while True:
            try:
                show_menu()
                choice = input("\nВаш выбор (0-5): ").strip()

                if choice == "0":
                    print("👋 До свидания!")
                    break

                elif choice == "1":
                    print("\n🤖 Запуск трейдера...")
                    print("🚦 Нажмите Ctrl+C для остановки")
                    print("=" * 50)
                    try:
                        trader.run_main_loop(sleep_duration=300)
                    except KeyboardInterrupt:
                        print("\n⏹️  Трейдер остановлен пользователем")

                elif choice == "2":
                    handle_leverage_menu(trader)

                elif choice == "3":
                    print("\n⚠️  ЗАКРЫТИЕ ВСЕХ ПОЗИЦИЙ")
                    status = trader.get_portfolio_status()
                    open_positions = status.get('open_positions', {})

                    if not open_positions:
                        print("✅ Нет открытых позиций")
                    else:
                        print(f"📍 Открытые позиции: {list(open_positions.keys())}")
                        confirm = input("Закрыть ВСЕ позиции? (yes/no): ").strip().lower()

                        if confirm == 'yes':
                            print("🔄 Закрытие позиций...")
                            success = trader.close_all_positions()
                            if success:
                                print("✅ Все позиции закрыты успешно!")
                            else:
                                print("❌ Ошибка при закрытии позиций!")
                        else:
                            print("❌ Операция отменена")

                    input("\nНажмите Enter для продолжения...")

                elif choice == "4":
                    print("\n⚖️  ПРИНУДИТЕЛЬНАЯ РЕБАЛАНСИРОВКА")
                    confirm = input("Выполнить принудительную ребалансировку? (yes/no): ").strip().lower()

                    if confirm == 'yes':
                        print("🔄 Выполнение ребалансировки...")
                        success = trader.force_rebalance()
                        if success:
                            print("✅ Ребалансировка завершена успешно!")
                        else:
                            print("❌ Ошибка при ребалансировке!")
                    else:
                        print("❌ Операция отменена")

                    input("\nНажмите Enter для продолжения...")

                elif choice == "5":
                    show_portfolio_status(trader)
                    input("\nНажмите Enter для продолжения...")

                else:
                    print("❌ Некорректный выбор! Попробуйте снова.")
                    input("\nНажмите Enter для продолжения...")

            except KeyboardInterrupt:
                print("\n\n🛑 Получен сигнал прерывания...")
                print("👋 До свидания!")
                break

    except KeyboardInterrupt:
        print("\n⏹️  Получен сигнал прерывания, завершение работы...")
    except Exception as e:
        print(f"\n💥 КРИТИЧЕСКАЯ ОШИБКА: {e}")
        # Логируем полную ошибку в файл
        import logging
        logging.error(f"Critical error: {e}", exc_info=True)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)
    finally:
        log_session_end()


if __name__ == "__main__":
    main()
