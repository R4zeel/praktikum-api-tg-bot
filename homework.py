import sys
import os
import time
import json
import logging

from http import HTTPStatus

import telegram
import requests

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


class RequestResponseError(Exception):
    """Исключение для ошибок при запросе."""

    pass


class WrongResponseStatusError(Exception):
    """Исключение для ошибок при запросе."""

    pass


class InsufficientTokensError(Exception):
    """Исключение для отсутствующих токенов."""

    pass


class EmptyListError(Exception):
    """Исключение при отсутствии элементов в списке."""

    pass


def check_tokens():
    """Проверяет доступность переменных окружения."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID
    }
    missing_tokens = []
    for key, value in tokens.items():
        if not value:
            logger.critical(
                f'Insufficient token: {key}',
                exc_info=True
            )
            missing_tokens.append(key)
    if not missing_tokens:
        return True
    return False


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
    # Добавил к каждой ошибке свой класс исключений
    except requests.RequestException as error:
        raise RequestResponseError(f'Request {api_answer} failed '
                                   f'with params: {timestamp}. '
                                   f'Error: {error}.')
    if api_answer.status_code != HTTPStatus.OK:
        raise WrongResponseStatusError(
            f'Failed request: {api_answer}. '
            f'Status code: {api_answer.status_code}.'
        )
    try:
        return api_answer.json()
    except json.JSONDecodeError:
        raise APIResponseError('Response is not parsable')


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
    logger.debug('Homework is empty', exc_info=True)


def parse_status(homework):
    """Извлекает статус домашней работы."""
    if not isinstance(homework, dict):
        raise TypeError('Homework is not a dict')
    if 'homework_name' not in homework:
        raise KeyError('Homework not found')
    homework_name = homework.get('homework_name')
    try:
        status = homework.get('status')
    except KeyError:
        KeyError('Got no status from homework')
    try:
        verdict = HOMEWORK_VERDICTS[status]
    except KeyError:
        raise KeyError(f'Status is not recognized{status}')
    if verdict == 'rejected':
        return homework.get('reviewer_comment')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        raise InsufficientTokensError('Insufficient tokens')
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    previous_status = ''

    while True:
        try:
            response = get_api_answer(timestamp)
            homework = check_response(response)
            try:
                status = parse_status(homework)
            except TypeError:
                logger.debug('Homework is not a dict', exc_info=True)
                time.sleep(RETRY_PERIOD)
                continue
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
