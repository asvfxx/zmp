import asyncio
import json
import logging
import re
import os
from datetime import datetime, timedelta
from telethon import TelegramClient, errors

# Глобальный флаг для остановки бота
stop_flag = False

# Конфигурация
CONFIG = {
    'API_ID': 29514367,  # Твой API ID
    'API_HASH': 'f8c6ed30b29ca0617db6ebf66618c55d',  # Твой API Hash
    'TARGET_BOT': '@zmpgamebot',
    'NOTIFY_CHAT': 'me',  # Уведомления в личный чат
    'SESSION_NAME': 'user_session',
    'DEFAULT_CRY_INTERVAL': 6 * 3600,  # 6 часов
    'DEFAULT_DI_INTERVAL': 24 * 3600,  # 24 часа
    'LOG_INTERVAL': 10 * 60,  # 10 минут
    'RETRY_DELAY': 60,  # Задержка при ошибке (сек)
    'MESSAGE_TIMEOUT': 5,  # Таймаут ответа (сек)
    'BET_PERCENTAGE': 0.5,  # Процент баланса для ставки (50%)
    'MIN_BALANCE': 10,  # Минимальный баланс
    'STATE_FILE': 'bot_state.json',
    'GAME_HISTORY_FILE': 'game_history.csv',
}

# Настройка логирования
logging.basicConfig(
    filename='farmbot.log',
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    encoding='utf-8'
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
console.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s'))
logging.getLogger('').addHandler(console)
logging.getLogger('telethon').setLevel(logging.WARNING)  # Игнорируем сообщения Telethon
logger = logging.getLogger(__name__)

class ZMPGameBot:
    """Класс для автоматизации взаимодействия с ботом @zmpgamebot."""

    def __init__(self):
        # Без прокси
        self.client = TelegramClient(CONFIG['SESSION_NAME'], CONFIG['API_ID'], CONFIG['API_HASH'])
        self.balance = 0
        self.loss_counts = {i: 0 for i in range(1, 7)}
        self.win_counts = {i: 0 for i in range(1, 7)}
        self.last_cry_time = 0.0
        self.last_di_time = 0.0
        self.top_position = 0  # Место в топе
        self.load_state()

    def load_state(self):
        """Загружает состояние бота из файла."""
        try:
            if os.path.exists(CONFIG['STATE_FILE']):
                with open(CONFIG['STATE_FILE'], 'r') as f:
                    state = json.load(f)
                    self.balance = state.get('balance', 0)
                    self.loss_counts = state.get('loss_counts', {i: 0 for i in range(1, 7)})
                    self.win_counts = state.get('win_counts', {i: 0 for i in range(1, 7)})
                    self.last_cry_time = state.get('last_cry_time', 0.0)
                    self.last_di_time = state.get('last_di_time', 0.0)
                    self.top_position = state.get('top_position', 0)
                    logger.info('ℹ️ Состояние бота загружено.')
                    logger.info(f'  Загруженные значения: last_cry_time={self.last_cry_time}, last_di_time={self.last_di_time}')
            else:
                logger.info('ℹ️ Файл состояния не найден, используются значения по умолчанию.')
        except Exception as e:
            logger.error(f'❌ Ошибка при загрузке состояния: {e}')

    def save_state(self):
        """Сохраняет состояние бота в файл."""
        try:
            with open(CONFIG['STATE_FILE'], 'w') as f:
                json.dump({
                    'balance': self.balance,
                    'loss_counts': self.loss_counts,
                    'win_counts': self.win_counts,
                    'last_cry_time': self.last_cry_time,
                    'last_di_time': self.last_di_time,
                    'top_position': self.top_position
                }, f, indent=4)
            logger.info('ℹ️ Состояние бота сохранено.')
        except Exception as e:
            logger.error(f'❌ Ошибка при сохранении состояния: {e}')

    def log_game_result(self, bet: int, number: int, result: str):
        """Записывает результат игры в CSV."""
        try:
            if not os.path.exists(CONFIG['GAME_HISTORY_FILE']):
                with open(CONFIG['GAME_HISTORY_FILE'], 'w', encoding='utf-8') as f:
                    f.write('Timestamp,Bet,Number,Result,Balance\n')
            with open(CONFIG['GAME_HISTORY_FILE'], 'a', encoding='utf-8') as f:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                f.write(f'{timestamp},{bet},{number},{result},{self.balance}\n')
            logger.info('📊 Результат игры сохранен.')
        except Exception as e:
            logger.error(f'❌ Ошибка при записи в историю: {e}')

    async def send_notification(self, message: str):
        """Отправляет уведомление в Telegram."""
        try:
            await self.client.send_message(CONFIG['NOTIFY_CHAT'], message)
            logger.info(f'📩 Уведомление отправлено: {message}')
        except Exception as e:
            logger.error(f'❌ Ошибка при отправке уведомления: {e}')

    @staticmethod
    def parse_time_to_sec(text: str) -> int | None:
        """Парсит время из текста в секунды (например, '1ч 30м' -> 5400)."""
        h = m = s = 0
        if match_h := re.search(r'(\d+)\s*ч', text):
            h = int(match_h.group(1))
        if match_m := re.search(r'(\d+)\s*м', text):
            m = int(match_m.group(1))
        if match_s := re.search(r'(\d+)\s*с', text):
            s = int(match_s.group(1))
        total = h * 3600 + m * 60 + s
        return total if total > 0 else None

    @staticmethod
    def format_seconds(seconds: int) -> str:
        """Форматирует секунды в строку (например, 3665 -> '1ч 1м')."""
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        parts = []
        if h > 0:
            parts.append(f'{h}ч')
        if m > 0:
            parts.append(f'{m}м')
        if s > 0 and h == 0:
            parts.append(f'{s}с')
        return ' '.join(parts) if parts else '0с'

    @staticmethod
    def absolute_time_str(seconds_from_now: int) -> str:
        """Возвращает абсолютное время в формате HH:MM:SS."""
        abs_time = datetime.now() + timedelta(seconds=seconds_from_now)
        return abs_time.strftime('%H:%M:%S')

    async def send_message(self, message: str) -> bool:
        """Отправляет сообщение боту с повторными попытками."""
        try:
            await self.client.send_message(CONFIG['TARGET_BOT'], message)
            logger.info(f'📤 Отправлена команда: {message}')
            return True
        except errors.FloodWaitError as e:
            wait = e.seconds
            logger.error(f'⏳ Flood wait на {wait} сек при отправке {message}')
            await asyncio.sleep(wait)
            return False
        except errors.RPCError as e:
            logger.error(f'❌ Ошибка Telegram API при отправке {message}: {e}')
            return False
        except Exception as e:
            logger.error(f'❌ Неизвестная ошибка при отправке {message}: {e}')
            return False

    async def get_last_message(self) -> str | None:
        """Получает последнее сообщение от бота."""
        try:
            async for message in self.client.iter_messages(CONFIG['TARGET_BOT'], limit=1):
                return message.message
        except Exception as e:
            logger.error(f'❌ Ошибка при получении сообщения: {e}')
        return None

    async def parse_balance(self, text: str) -> tuple[int | None, int | None]:
        """Парсит баланс и место в топе из текста."""
        balance = None
        top_position = None
        if match_balance := re.search(r'• Текущие слёзы:\s*(\d+)', text):
            balance = int(match_balance.group(1))
        if match_top := re.search(r'• Твоё место в топе:\s*(\d+)', text):
            top_position = int(match_top.group(1))
        return balance, top_position

    def choose_bet_number(self) -> int:
        """Выбирает число для ставки с наименьшим количеством проигрышей."""
        number = min(self.loss_counts, key=self.loss_counts.get)
        scores = {i: self.win_counts[i] / (self.loss_counts[i] + 1) for i in range(1, 7)}
        logger.info(f'🎲 Выбрано число {number} (выигрыши: {self.win_counts}, проигрыши: {self.loss_counts}, вероятности: {scores})')
        return number

    async def log_remaining_time(self, cry_wait: int, di_wait: int):
        """Логирует время до следующего действия и статистику."""
        logger.info('═' * 50)
        logger.info('🕒 Периодический отчет')
        logger.info(f'  Баланс: {self.balance} слёз')
        logger.info(f'  Место в топе: {self.top_position if self.top_position else "Неизвестно"}')
        logger.info(f'  Статистика выигрышей: {self.win_counts}')
        logger.info(f'  Статистика проигрышей: {self.loss_counts}')
        logger.info(f'  Время до /cry: {self.format_seconds(cry_wait)} (в {self.absolute_time_str(cry_wait)})')
        logger.info(f'  Время до /di: {self.format_seconds(di_wait)} (в {self.absolute_time_str(di_wait)})')
        logger.info('═' * 50)

    async def farm_cycle(self):
        """Основной цикл фарма."""
        last_log_time = asyncio.get_event_loop().time()
        logger.info('═' * 50)
        logger.info('🚀 Начало цикла фарма')
        logger.info('═' * 50)

        while True:
            if stop_flag:
                logger.info('🛑 Бот остановлен командой /stop.')
                await self.client.disconnect()
                break

            try:
                now = asyncio.get_event_loop().time()
                cry_wait = max(0, int(self.last_cry_time - now))  # Оставшееся время до /cry
                di_wait = max(0, int(self.last_di_time - now))    # Оставшееся время до /di
                logger.info(f'⏳ Вычисленное время ожидания: cry_wait={self.format_seconds(cry_wait)}, di_wait={self.format_seconds(di_wait)}')

                # Периодический отчет каждые 10 минут
                if now - last_log_time >= CONFIG['LOG_INTERVAL']:
                    await self.log_remaining_time(cry_wait, di_wait)
                    last_log_time = now
                    logger.info(f'📝 Обновлено last_log_time: {last_log_time}')

                # Команда /cry (отправляется, если время истекло)
                if cry_wait == 0:
                    logger.info('✅ Время для /cry истекло, отправляем команду.')
                    if await self.send_message('/cry'):
                        await asyncio.sleep(CONFIG['MESSAGE_TIMEOUT'])
                        reply = await self.get_last_message()
                        if reply:
                            logger.info(f'📨 Ответ на /cry:\n{reply}')
                            if 'Ты уже плакал' in reply:
                                wait_sec = self.parse_time_to_sec(reply) or CONFIG['DEFAULT_CRY_INTERVAL']
                                self.last_cry_time = now + wait_sec
                                logger.info(f'⏱ /cry недоступен. Следующая попытка через {self.format_seconds(wait_sec)}.')
                            else:
                                self.last_cry_time = now + CONFIG['DEFAULT_CRY_INTERVAL']
                                if m := re.search(r'Теперь у тебя (\d+) сл', reply):
                                    self.balance = int(m.group(1))
                                    logger.info(f'ℹ️ Баланс обновлен: {self.balance}')
                                    if self.balance >= CONFIG['MIN_BALANCE'] * 2:
                                        await self.send_notification(f'Баланс увеличен до {self.balance} слёз!')
                            self.save_state()
                        else:
                            logger.warning('❗ Нет ответа на /cry')
                            await self.send_notification('⚠️ Нет ответа на /cry')
                            await asyncio.sleep(CONFIG['RETRY_DELAY'])
                            continue
                    else:
                        await asyncio.sleep(CONFIG['RETRY_DELAY'])
                        continue
                else:
                    logger.info(f'⏳ /cry еще недоступен, осталось ждать {self.format_seconds(cry_wait)}.')

                # Команда /my (выполняется регулярно для обновления статуса)
                if await self.send_message('/my'):
                    await asyncio.sleep(CONFIG['MESSAGE_TIMEOUT'])
                    reply = await self.get_last_message()
                    if reply:
                        logger.info(f'📨 Ответ на /my:\n{reply}')
                        balance, top_position = await self.parse_balance(reply)
                        if balance is not None:
                            if balance != self.balance:
                                self.balance = balance
                                logger.info(f'ℹ️ Баланс обновлен: {self.balance}')
                        if top_position is not None:
                            if top_position != self.top_position:
                                self.top_position = top_position
                                logger.info(f'ℹ️ Место в топе обновлено: {self.top_position}')
                        if balance is None:
                            logger.warning('❗ Не удалось распарсить баланс из /my')
                        self.save_state()
                    else:
                        logger.warning('❗ Нет ответа на /my')
                        await self.send_notification('⚠️ Нет ответа на /my')
                        await asyncio.sleep(CONFIG['RETRY_DELAY'])
                        continue
                else:
                    await asyncio.sleep(CONFIG['RETRY_DELAY'])
                    continue

                # Команда /di (отправляется, если время истекло и достаточно баланса)
                now = asyncio.get_event_loop().time()
                di_wait = max(0, int(self.last_di_time - now))
                if di_wait == 0 and self.balance >= CONFIG['MIN_BALANCE']:
                    logger.info('✅ Время для /di истекло, отправляем команду.')
                    bet = max(1, int(self.balance * CONFIG['BET_PERCENTAGE']))
                    number = self.choose_bet_number()
                    cmd = f'/di {bet} {number}'
                    if await self.send_message(cmd):
                        await asyncio.sleep(CONFIG['MESSAGE_TIMEOUT'])
                        reply = await self.get_last_message()
                        if reply:
                            logger.info(f'📨 Ответ на {cmd}:\n{reply}')
                            if 'Ты выиграл' in reply:
                                self.balance += bet
                                self.win_counts[number] += 1
                                self.loss_counts[number] = max(0, self.loss_counts[number] - 1)
                                logger.info(f'🎉 Выигрыш! Баланс: {self.balance}')
                                self.log_game_result(bet, number, 'Win')
                                await self.send_notification(f'🎉 Выиграл {bet} слёз! Баланс: {self.balance}')
                                self.last_di_time = now + CONFIG['DEFAULT_DI_INTERVAL']
                            elif 'Ты не угадал' in reply or 'проиграл' in reply:
                                self.balance -= bet
                                self.loss_counts[number] += 1
                                logger.info(f'😞 Проигрыш. Баланс: {self.balance}')
                                self.log_game_result(bet, number, 'Loss')
                                await self.send_notification(f'😞 Проиграл {bet} слёз. Баланс: {self.balance}')
                                self.last_di_time = now + CONFIG['DEFAULT_DI_INTERVAL']
                            self.save_state()
                        else:
                            logger.warning('❗ Нет ответа на /di')
                            await self.send_notification('⚠️ Нет ответа на /di')
                            await asyncio.sleep(CONFIG['RETRY_DELAY'])
                            continue
                    else:
                        await asyncio.sleep(CONFIG['RETRY_DELAY'])
                        continue
                else:
                    logger.info(f'⏳ /di еще недоступен, осталось ждать {self.format_seconds(di_wait)} или баланс {self.balance} < {CONFIG["MIN_BALANCE"]}.')

                # Задержка перед следующей итерацией
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f'❌ Критическая ошибка в цикле: {e}')
                await self.send_notification(f'⚠️ Критическая ошибка: {e}')
                await asyncio.sleep(CONFIG['RETRY_DELAY'])

    async def start(self):
        """Запускает бота."""
        try:
            await self.client.start(phone='+39 351 447 7989',
            code_callback=lambda: '92333')
            logger.info('✅ Бот запущен.')
            await self.farm_cycle()
        except Exception as e:
            logger.error(f'❌ Ошибка при запуске бота: {e}')
            await self.send_notification(f'⚠️ Ошибка при запуске: {e}')

async def main():
    """Основная функция запуска."""
    bot = ZMPGameBot()
    await bot.start()

if __name__ == "__main__":
    asyncio.run(main())
