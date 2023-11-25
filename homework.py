import sys

import telegram

import logging
import os
import requests

import time

from dotenv import load_dotenv

from logging import StreamHandler

from http import HTTPStatus

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


class APIResponseError(Exception):
    """Исключение для некорректного содержания ответа API."""

    pass


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
        api_answer.raise_for_status()
        if api_answer.status_code == HTTPStatus.NO_CONTENT:
            logger.exception('Invalid status code')
            raise HTTPStatus.NO_CONTENT
        return api_answer.json()
    except requests.RequestException:
        logger.error('Status error', exc_info=True)
        # Тут пытался добавить raise,
        # но такая конструкция не проходит тесты


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if type(response) is not dict:
        logger.exception(f'Wrong response type {response}')
        raise TypeError(f'Wrong response type {response}')
    homework = response.get('homeworks')
    if 'homeworks' not in response or 'current_date' not in response:
        logger.exception('Homeworks not found')
        raise APIResponseError(f'{response}')
    if type(response['homeworks']) is not list:
        logger.exception('Homeworks is not a list')
        raise TypeError
    return homework[0]


def parse_status(homework):
    """Извлекает статус домашней работы."""
    # странная конструкция, но без if у меня не удалось пройти тест
    if 'homework_name' in homework:
        try:
            homework_name = homework.get('homework_name')
        except KeyError:
            logger.error('Homework not found', exc_info=True)
            raise KeyError
    try:
        homework.get('status')
    except KeyError:
        logger.error('Status is not recognized', exc_info=True)
        raise KeyError
    try:
        verdict = HOMEWORK_VERDICTS[homework.get('status')]
    except KeyError:
        logger.error('Status is not recognized', exc_info=True)
        raise KeyError

    if verdict == 'rejected':
        return homework.get('reviewer_comment')
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
            response = get_api_answer(timestamp)
            homework = check_response(response)
            status = parse_status(homework)
            if status == previous_status:
                logger.debug('No new statuses found', exc_info=True)
                continue
            previous_status = status
            send_message(bot, status)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(error, exc_info=True)
            send_message(bot, message)
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
