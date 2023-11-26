import sys
import os
import time
import json

import telegram
import logging
import requests

from http import HTTPStatus

from dotenv import load_dotenv


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
handler = logging.StreamHandler()
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
            logger.critical(
                f'Insufficient token: {token}',
                exc_info=True
            )
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
        # Думал такой конструкцией проверять ошибку при получении
        # ответа(RequestException для этого не подойдёт?), но судя по
        # всему, из-за того, что в тестах используются данного типа -
        # на тестах получаю ошибку.
        # if not isinstance(api_answer, requests.Response):
        #     raise APIResponseError(
        #         f'Wrong response: {type(api_answer)}'
        #     )
        if api_answer.status_code != HTTPStatus.OK:
            raise APIResponseError(
                f'Failed request: {api_answer}. '
                f'Status code: {api_answer.status_code}.'
            )
        try:
            return api_answer.json()
        except json.JSONDecodeError:
            raise APIResponseError('Response is not parsable')
    except requests.RequestException as error:
        logger.error(f'Request error: {error}', exc_info=True)
        # Пытался добавлять RequestException в raise,
        # так не работало - получаю ошибку о том, что
        # при таком исключении оно не обрабатывается.
        # Добавил кастомный класс исключений - тест прошёл.
        raise APIResponseError(f'Request error: {error}')


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError(f'Wrong response type {response}')
    homework = response.get('homeworks')
    if 'homeworks' not in response or 'current_date' not in response:
        raise APIResponseError(f'{response}')
    if not isinstance(response['homeworks'], list):
        raise TypeError(f'homeworks is not a list: {type(homework)}')
    if homework:
        return homework[0]
    return homework


def parse_status(homework):
    """Извлекает статус домашней работы."""
    if isinstance(homework, dict):
        if 'homework_name' in homework:
            homework_name = homework.get('homework_name')
        else:
            raise KeyError('Homework not found')
    else:
        raise TypeError('Homework is not a dict')
    try:
        verdict = HOMEWORK_VERDICTS[homework.get('status')]
    except KeyError:
        raise KeyError('Status is not recognized')

    if verdict == 'rejected':
        return homework.get('reviewer_comment')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if check_tokens():
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
    else:
        raise SystemExit('Insufficient tokens')
    timestamp = int(time.time())
    previous_status = ''

    while True:
        try:
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
        timestamp = int(time.time())


if __name__ == '__main__':
    main()
