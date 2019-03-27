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
        validate_config(config)
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
            'username') and jira.get('api_token') and
            jira.get('project_key')):
        logger.info('`api_url`, `username`, `api_token` and `project_key` '
                    'are required for `jira` field.')
        exit(1)


def get_auth_token(config):

    usm = config['usm']
    url = urljoin(usm.get('api_url'), 'oauth/token')
    logger.info('Retreving OAUTH token for USM...')
    res = requests.post(url, data={'grant_type': 'client_credentials'},
                        auth=(usm.get('client_id'), usm.get('client_secret')))

    if res.status_code < 300:
        return res.json().get('access_token')

    logger.info('Unexpected response returned: %s', res)
    return None


def get_usm_alarms(config, token):

    usm = config['usm']
    curr_time = str(time.time()).replace('.', str())[:13]
    prev_time = str(int(curr_time) - (
        config.get('usm_interval', 10) * 60 * 1000))
    params = ['sort=timestamp_occured,desc',
              'timestamp_occured_gte=' + prev_time]

    url = urljoin(usm.get('api_url'), 'alarms?%s' % ('&'.join(params)))
    logger.info('Retrieving USM alarms...')
    res = requests.get(url, headers={'Authorization': 'Bearer ' + token})
    if res.status_code < 300:
        alarms = res.json().get('_embedded', dict()).get('alarms', list())
        logger.info('[%d] alarms fetched from USM.', len(alarms))
        logger.info(str())
        return alarms

    logger.info('Unexpected response returned: %s', res)
    return None


def get_jira_projects(config):

    jira = config['jira']
    url = urljoin(jira.get('api_url'), 'project/search')
    logger.info('Retrieving JIRA projects...')

    query = {
        'maxResults': 100,
        'fields': ['id', 'key', 'name']}

    logger.debug('Using query: %s', query)
    res = requests.get(url, json=query, auth=(
        jira.get('username'), jira.get('api_token')))

    if res.status_code < 300:
        projects = list()
        for value in res.json().get('values', list()):
            projects.append({
                key: value for (key, value) in value.items()
                if key in query['fields']
            })
        logger.info('[%d] projects fetched from JIRA.', len(projects))
        logger.info(str())
        return projects

    logger.info('Unexpected response returned: %s', res)
    return None


def get_jira_issue_types(config):

    jira = config['jira']
    url = urljoin(jira.get('api_url'), 'issuetype')
    logger.info('Retrieving JIRA issue types...')

    query = {'fields': ['id', 'name', 'subtask']}
    logger.debug('Using query: %s', query)
    res = requests.get(url, auth=(jira.get('username'), jira.get('api_token')))

    if res.status_code < 300:
        projects = list()
        for value in res.json():
            projects.append({
                key: value for (key, value) in value.items()
                if key in query['fields']
            })
        logger.info('[%d] issue types fetched from JIRA.', len(projects))
        logger.info(str())
        return projects

    logger.info('Unexpected response returned: %s', res)
    return None


def get_jira_issues(config):

    jira = config['jira']
    url = urljoin(jira.get('api_url'), 'search')
    logger.info('Retrieving JIRA issues...')

    if not(jira.get('project_key') and config.get('interval')):
        logger.info('JIRA project and/or interval for issues are '
                    'missing in config. Only the latest 100 issues '
                    'will be considered.')

    query = dict()
    query['maxResults'] = 100
    query['fields'] = ['assignee', 'summary',
                       'description', 'created', 'updated']
    if jira.get('project_key') or config.get('interval'):
        jql = list()
        jql.append('project = %s' % (jira['project_key'])
                   if jira.get('project_key') else str())
        jql.append('created > -%sm' % (config['interval'])
                   if config.get('interval') else str())

        jql = ' AND '.join([x for x in jql if x])
        query['jql'] = jql

    logger.debug('Using query: %s', query)
    res = requests.post(url, json=query, auth=(
        jira.get('username'), jira.get('api_token')))

    if res.status_code < 300:
        issues = res.json().get('issues', list())
        logger.info('[%d] issues fetched from JIRA.', len(issues))
        logger.info(str())

        for issue in issues:
            url = urljoin(
                jira.get('api_url'),
                'issue/%s/properties/usm_data' % issue.get('id'))

            res = requests.get(url, auth=(
                jira.get('username'), jira.get('api_token')))

            if res.status_code < 300 and res.json().get('value'):
                issue['properties'] = res.json().get('value')

        return issues

    logger.info('Unexpected response returned: %s', res)
    return list()


def filter_alarms(alarms, issues, config):

    filtered = list()
    usm = config['usm']
    if not(usm.get('alarms') and usm['alarms'].get('titles')):
        logger.info('No alarm titles specified in config. '
                    'Skipping all alarms...')
        return filtered

    titles = usm['alarms']['titles']
    posted_uuids = [x['properties']['alarm-uuid'] for x in issues if x.get(
        'properties', dict()).get('alarm-uuid')]

    for alarm in alarms:
        if alarm['uuid'] not in posted_uuids and \
                alarm.get('rule_strategy', str()) in titles:
            filtered.append(alarm)

    logger.info('[%d] alarms remained after filtering out already '
                'posted ones.', len(filtered))
    return filtered


def tickets_from_alarms(alarms):

    tickets = list()
    for alarm in alarms:
        ticket = dict()
        ticket['uuid'] = alarm['uuid']
        ticket['title'] = alarm['rule_strategy']
        ticket['timestamp'] = alarm['timestamp_occured_iso8601']
        ticket['method'] = alarm['rule_method']
        ticket['priority'] = alarm['priority_label']
        ticket['sources'] = alarm['alarm_source_names']
        ticket['dests'] = alarm['alarm_destination_names']
        ticket['description'] = 'Template description will come here.'
        ticket['remediation'] = 'Template remediation will come here.'
        tickets.append(ticket)

    return tickets


def push_tickets(tickets, projects, issue_types, config):

    data = {
        'fields': {
            'summary': '{title}',
            'project': {'id': '{project_id}'},
            'issuetype': {'id': '{issuetype_id}'},
            'description': '*{description}*\n-Baka-'
        }
    }

    project_id = 0
    jira = config['jira']

    for project in projects:
        if not(project.get('key') and project.get('id')):
            continue
        if project['key'] == jira.get('project_key'):
            project_id = project['id']
            break

    if not project_id:
        logger.info('Could not detect project id for pushing tickets to.')
        return

    issuetype_id = 0

    for itype in issue_types:
        if not(itype.get('name') and itype.get('id')):
            continue
        if itype['name'].lower() == jira.get('issue_type').lower():
            issuetype_id = itype['id']
            break

    if not issuetype_id:
        logger.info('Could not detect issue type id for pushing tickets with.')
        return

    logger.info('Pusing tickets to JIRA...')
    url = urljoin(jira.get('api_url'), 'issue')
    responses = dict()
    count = 0
    for ticket in tickets:
        ticket_data = json.dumps(data)
        ticket_data = ticket_data \
            .replace('{title}', ticket.get('title')) \
            .replace('{description}', ticket.get('description')) \
            .replace('{project_id}', project_id) \
            .replace('{issuetype_id}', issuetype_id) \

        ticket_data = json.loads(ticket_data)
        res = requests.post(url, json=ticket_data, auth=(
            jira.get('username'), jira.get('api_token')))
        responses[ticket['uuid']] = res.json()

        if res.status_code < 300:
            count += 1
            res = res.json()
            url = urljoin(
                jira.get('api_url'),
                'issue/%s/properties/usm_data' % (res.get('id')))

            requests.put(
                url, json={'alarm-uuid': ticket.get('uuid')},
                auth=(jira.get('username'), jira.get('api_token')))

    logger.info('[%d/%d] tickets pushed to JIRA successfully.',
                count, len(tickets))
    logger.info(str())
    return responses


if __name__ == "__main__":

    logger.info(str())
    config = read_config()
    token = get_auth_token(config)
    alarms = get_usm_alarms(config, token)

    issues = get_jira_issues(config)
    projects = get_jira_projects(config)
    issue_types = get_jira_issue_types(config)

    filtered_alarms = filter_alarms(alarms, issues, config)
    tickets = tickets_from_alarms(filtered_alarms)
    responses = push_tickets(tickets, projects, issue_types, config)
