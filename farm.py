import asyncio
import json
import logging
import re
import os
from datetime import datetime, timedelta
from telethon import TelegramClient, errors

# Конфигурация
CONFIG = {
    'API_ID': 29514367,
    'API_HASH': 'f8c6ed30b29ca0617db6ebf66618c55d',
    'TARGET_BOT': '@zmpgamebot',
    'NOTIFY_CHAT': 'me',
    'SESSION_NAME': 'user_session',
    'DEFAULT_CRY_INTERVAL': 6 * 3600,  # 6 часов
    'LOG_INTERVAL': 10 * 60,  # 10 минут
    'RETRY_DELAY': 60,
    'MESSAGE_TIMEOUT': 5,
    'STATE_FILE': 'bot_state.json',
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
logging.getLogger('telethon').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

class ZMPGameBot:
    def __init__(self):
        self.client = TelegramClient(CONFIG['SESSION_NAME'], CONFIG['API_ID'], CONFIG['API_HASH'])
        self.balance = 0
        self.last_cry_time = 0.0
        self.top_position = 0
        self.load_state()

    def load_state(self):
        try:
            if os.path.exists(CONFIG['STATE_FILE']):
                with open(CONFIG['STATE_FILE'], 'r') as f:
                    state = json.load(f)
                    self.balance = state.get('balance', 0)
                    self.last_cry_time = state.get('last_cry_time', 0.0)
                    self.top_position = state.get('top_position', 0)
                    logger.info('ℹ️ Состояние бота загружено.')
                    logger.info(f'  Загруженные значения: last_cry_time={self.last_cry_time}')
            else:
                logger.info('ℹ️ Файл состояния не найден, используются значения по умолчанию.')
        except Exception as e:
            logger.error(f'❌ Ошибка при загрузке состояния: {e}')

    def save_state(self):
        try:
            with open(CONFIG['STATE_FILE'], 'w') as f:
                json.dump({
                    'balance': self.balance,
                    'last_cry_time': self.last_cry_time,
                    'top_position': self.top_position
                }, f, indent=4)
            logger.info('ℹ️ Состояние бота сохранено.')
        except Exception as e:
            logger.error(f'❌ Ошибка при сохранении состояния: {e}')

    async def send_notification(self, message: str):
        try:
            await self.client.send_message(CONFIG['NOTIFY_CHAT'], message)
            logger.info(f'📩 Уведомление отправлено: {message}')
        except Exception as e:
            logger.error(f'❌ Ошибка при отправке уведомления: {e}')

    async def send_message(self, message: str) -> bool:
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
        try:
            async for message in self.client.iter_messages(CONFIG['TARGET_BOT'], limit=1):
                return message.message
        except Exception as e:
            logger.error(f'❌ Ошибка при получении сообщения: {e}')
        return None

    @staticmethod
    def parse_time_to_sec(text: str) -> int | None:
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
        abs_time = datetime.now() + timedelta(seconds=seconds_from_now)
        return abs_time.strftime('%H:%M:%S')

    async def log_remaining_time(self, cry_wait: int):
        logger.info('═' * 50)
        logger.info('🕒 Периодический отчет')
        logger.info(f'  Баланс: {self.balance} слёз')
        logger.info(f'  Место в топе: {self.top_position if self.top_position else "Неизвестно"}')
        logger.info(f'  Время до /cry: {self.format_seconds(cry_wait)} (в {self.absolute_time_str(cry_wait)})')
        logger.info('═' * 50)

    async def parse_balance(self, text: str) -> tuple[int | None, int | None]:
        balance = None
        top_position = None
        if match_balance := re.search(r'• Текущие слёзы:\s*(\d+)', text):
            balance = int(match_balance.group(1))
        if match_top := re.search(r'• Твоё место в топе:\s*(\d+)', text):
            top_position = int(match_top.group(1))
        return balance, top_position

    async def start(self):
        await self.client.start()
        logger.info('✅ Бот запущен.')

        now = asyncio.get_event_loop().time()
        if await self.send_message('/cry'):
            await asyncio.sleep(CONFIG['MESSAGE_TIMEOUT'])
            reply = await self.get_last_message()
            if reply:
                logger.info(f'📨 Ответ на /cry:\n{reply}')
                if 'Ты уже плакал' in reply:
                    wait_sec = self.parse_time_to_sec(reply) or CONFIG['DEFAULT_CRY_INTERVAL']
                    self.last_cry_time = now + wait_sec
                    logger.info(f'⏱️ /cry недоступен. Следующая попытка через {self.format_seconds(wait_sec)}.')
                else:
                    self.last_cry_time = now + CONFIG['DEFAULT_CRY_INTERVAL']
                    if m := re.search(r'Теперь у тебя (\d+) сл', reply):
                        self.balance = int(m.group(1))
                        logger.info(f'ℹ️ Баланс обновлен: {self.balance}')
                        if self.balance >= 20:  # Убрал MIN_BALANCE * 2, заменил на фиксированное значение
                            await self.send_notification(f'Баланс увеличен до {self.balance} слёз!')
            else:
                logger.warning('❗️ Нет ответа на /cry, использую значение по умолчанию.')
                self.last_cry_time = now + CONFIG['DEFAULT_CRY_INTERVAL']
        else:
            logger.warning('❗️ Не удалось отправить /cry, использую значение по умолчанию.')
            self.last_cry_time = now + CONFIG['DEFAULT_CRY_INTERVAL']

        self.save_state()
        await self.farm_cycle()

    async def farm_cycle(self):
        last_log_time = asyncio.get_event_loop().time()
        logger.info('═' * 50)
        logger.info('🚀 Начало цикла фарма')
        logger.info('═' * 50)

        while True:
            try:
                now = asyncio.get_event_loop().time()
                cry_wait = max(0, int(self.last_cry_time - now))
                logger.info(f'⏳ Вычисленное время ожидания: cry_wait={self.format_seconds(cry_wait)}')

                if now - last_log_time >= CONFIG['LOG_INTERVAL']:
                    await self.log_remaining_time(cry_wait)
                    last_log_time = now

                if cry_wait == 0:
                    if await self.send_message('/cry'):
                        await asyncio.sleep(CONFIG['MESSAGE_TIMEOUT'])
                        reply = await self.get_last_message()
                        if reply:
                            logger.info(f'📨 Ответ на /cry:\n{reply}')
                            if 'Ты уже плакал' in reply:
                                wait_sec = self.parse_time_to_sec(reply) or CONFIG['DEFAULT_CRY_INTERVAL']
                                self.last_cry_time = now + wait_sec
                                logger.info(f'⏱️ /cry недоступен. Следующая попытка через {self.format_seconds(wait_sec)}.')
                            else:
                                self.last_cry_time = now + CONFIG['DEFAULT_CRY_INTERVAL']
                                if m := re.search(r'Теперь у тебя (\d+) сл', reply):
                                    self.balance = int(m.group(1))
                                    logger.info(f'ℹ️ Баланс обновлен: {self.balance}')
                                    if self.balance >= 20:
                                        await self.send_notification(f'Баланс увеличен до {self.balance} слёз!')
                            self.save_state()
                        else:
                            logger.warning('❗️ Нет ответа на /cry')
                            await self.send_notification('⚠️ Нет ответа на /cry')
                            await asyncio.sleep(CONFIG['RETRY_DELAY'])
                            continue
                else:
                    logger.info(f'⏳ /cry еще недоступен, осталось ждать {self.format_seconds(cry_wait)}.')

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
                        self.save_state()
                    else:
                        logger.warning('❗️ Нет ответа на /my')
                        await self.send_notification('⚠️ Нет ответа на /my')
                        await asyncio.sleep(CONFIG['RETRY_DELAY'])
                        continue

                sleep_time = cry_wait if cry_wait > 0 else 60
                logger.info(f'💤 Засыпаем на {self.format_seconds(sleep_time)} до следующего действия.')
                await asyncio.sleep(sleep_time)

            except Exception as e:
                logger.error(f'❌ Ошибка в цикле фарма: {e}')
                await self.send_notification(f'⚠️ Ошибка в работе бота: {e}')
                await asyncio.sleep(CONFIG['RETRY_DELAY'])

async def main():
    while True:
        try:
            bot = ZMPGameBot()
            await bot.start()
        except Exception as e:
            logger.error(f'❌ Критическая ошибка, перезапуск бота: {e}')
            await asyncio.sleep(60)

if __name__ == '__main__':
    asyncio.run(main())
