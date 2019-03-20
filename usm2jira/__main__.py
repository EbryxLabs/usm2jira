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


USM_API_URL = str()
CLIENT_ID = str()
CLIENT_SECRET = str()


def get_auth_token():

    url = urljoin(USM_API_URL, 'oauth/token')
    logger.info('Making POST request: %s', url)
    res = requests.post(url, data={'grant_type': 'client_credentials'},
                        auth=(CLIENT_ID, CLIENT_SECRET))

    if res.status_code < 300:
        return res.json().get('access_token')

    logger.info('Unexpected response returned: %s', res)
    return None


def get_usm_alarms(token):

    c_time = int(str(time.time()).split('.')[0])
    timestamp = str(c_time - (1 * 60))

    params = ['page=1', 'size=2', 'sort=timestamp_occured,desc',
              'timestamp_occured_gte=' + timestamp]

    url = urljoin(USM_API_URL, 'alarms?%s' % ('&'.join(params)))
    logger.info('Making GET request: %s', url)
    res = requests.get(url, headers={'Authorization': 'Bearer ' + token})
    if res.status_code < 300:
        return res.json().get('_embedded', dict()).get('alarms', list())

    logger.info('Unexpected response returned: %s', res)
    return None


if __name__ == "__main__":
    token = get_auth_token()
    alarms = get_usm_alarms(token)
    print(json.dumps(alarms, indent=2))
