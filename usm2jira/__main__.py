import os
import json
import time
import logging
import requests
from urllib.parse import urljoin


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setLevel(logging.INFO)
handler.setFormatter(logging.Formatter('%(asctime)s: %(message)s'))
logger.addHandler(handler)


def read_config():

    if not os.environ.get('CONFIG_FILE'):
        logger.info('No CONFIG_FILE environment variable is defined.')
        exit(1)

    if not os.path.isfile(os.environ.get('CONFIG_FILE')):
        logger.info('No file exists on CONFIG_FILE path defined.')
        exit(1)

    try:
        config = json.load(open(os.environ.get('CONFIG_FILE'), 'r'))
        return config
    except json.JSONDecodeError as exc:
        logger.info(exc)
        exit(1)


def validate_config(config):

    if not config.get('usm'):
        logger.info('No `usm` field defined in config.')
        exit(1)

    if not config.get('jira'):
        logger.info('No `jira` field defined in config.')
        exit(1)

    usm = config['usm']
    if not(usm.get('api_url') and usm.get(
            'client_id') and usm.get('client_secret')):
        logger.info('`api_url`, `client_id` and `client_secret` are '
                    'required for `usm` field.')
        exit(1)

    jira = config['jira']
    if not(jira.get('api_url') and jira.get(
            'username') and jira.get('api_token')):
        logger.info('`api_url`, `username` and `api_token` are required '
                    'for `jira` field.')
        exit(1)


def get_auth_token(config):

    usm = config['usm']
    url = urljoin(usm.get('api_url'), 'oauth/token')
    logger.info('Making POST request: %s', url)
    res = requests.post(url, data={'grant_type': 'client_credentials'},
                        auth=(usm.get('client_id'), usm.get('client_secret')))

    if res.status_code < 300:
        return usm.get('api_url'), res.json().get('access_token')

    logger.info('Unexpected response returned: %s', res)
    return None, None


def get_usm_alarms(api_url, token):

    c_time = int(str(time.time()).split('.')[0])
    timestamp = str(c_time - (1 * 60))

    params = ['page=1', 'size=2', 'sort=timestamp_occured,desc',
              'timestamp_occured_gte=' + timestamp]

    url = urljoin(api_url, 'alarms?%s' % ('&'.join(params)))
    logger.info('Making GET request: %s', url)
    res = requests.get(url, headers={'Authorization': 'Bearer ' + token})
    if res.status_code < 300:
        return res.json().get('_embedded', dict()).get('alarms', list())

    logger.info('Unexpected response returned: %s', res)
    return None


if __name__ == "__main__":

    config = read_config()
    api_url, token = get_auth_token(config)
    alarms = get_usm_alarms(api_url, token)
    print(json.dumps(alarms, indent=2))
