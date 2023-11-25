import sys

import telegram

import logging
import os
import requests

import time

from dotenv import load_dotenv

from logging import StreamHandler

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = StreamHandler()
handler.setStream(sys.stdout)
logger.addHandler(handler)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
handler.setFormatter(formatter)


def check_tokens():
    """Проверяет доступность переменных окружения."""
    tokens = [
        PRACTICUM_TOKEN,
        TELEGRAM_TOKEN,
        TELEGRAM_CHAT_ID
    ]

    for token in tokens:
        if not token:
            logger.critical('Insufficient env variables',
                            exc_info=True)
            return False
    return True


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    try:
        bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
        )
        logger.debug('message sent successfully', exc_info=True)
    except Exception as error:
        logger.error(error, exc_info=True)


def get_api_answer(timestamp):
    """Делает запрос к API."""
    try:
        api_answer = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp}
        )
    except requests.RequestException:
        logger.error('Status error', exc_info=True)
    finally:
        if not api_answer.status_code == 200:
            logger.error(f'Response status: {api_answer.status_code}')
        if check_response(api_answer.json()):
            return api_answer.json()


def check_response(response: dict):
    """Проверяет ответ API на соответствие документации."""
    if type(response) is not dict:
        logger.exception('Response is not dict')
        raise TypeError
    elif 'homeworks' not in response:
        logger.error('Insufficient dict keys', exc_info=True)
        raise KeyError
    elif type(response['homeworks']) is not list:
        logger.exception('Wrong homeworks type')
        raise TypeError
    return True


def parse_status(homework):
    """Извлекает статус домашней работы."""
    status = get_api_answer(homework)
    status = status.get('homeworks')
    try:
        homework_name = status[0].get('homework_name')
    except IndexError:
        logger.error('Homework not found', exc_info=True)
        return 'Домашняя работа не найдена'
    try:
        verdict = HOMEWORK_VERDICTS[status[0].get('status')]
    except KeyError:
        logger.error('Status is not recognized', exc_info=True)
        return 'Статус неизвестен'

    if verdict == 'rejected':
        return status[0].get('reviewer_comment')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'

# Не смог додуматься, как и стоит ли отправлять ТГ
# сообщения об ошибках из функций выше - объявлять
# для таких сообщений отдельную функцию? Также не знаю,
# как при отправке таких сообщений обойтись без
# использования циклов с переменной запоминающей
# предыдущее значение. Если нужно отправлять сообщение
# один раз - то такую конструкицю придётся использовать
# при каждом логгировании. Ограничился ошибками в ТГ
# только в main функции.


def main():
    """Основная логика работы бота."""
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    previous_status = str()

    while True:
        try:
            if not check_tokens():
                raise SystemExit
            status = parse_status(timestamp)
            if status == previous_status:
                logger.debug('No new statuses found', exc_info=True)
                continue
            previous_status = status
            send_message(bot, status)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(error, exc_info=True)
            send_message(bot, message)
        time.sleep(600)


if __name__ == '__main__':
    main()
