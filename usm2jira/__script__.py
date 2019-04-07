import os
import re
import time
import json
import time
import logging
import hashlib
import requests
import opencrypt
from urllib.parse import urljoin


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setLevel(logging.INFO)
handler.setFormatter(logging.Formatter('%(asctime)s: %(message)s'))
logger.addHandler(handler)


def read_config():

    if not os.environ.get('CONFIG_FILE'):
        exit('No CONFIG_FILE environment variable exists.\n')

    config_file = os.environ['CONFIG_FILE']
    if config_file.startswith(('http', 'https', 'ftp')):
        logger.info('Config file prefix tells program to fetch it online.')
        logger.info('Fetching config file: %s' % (config_file))
        response = requests.get(config_file)

        if response.status_code < 400:
            ciphertext = response.content
        else:
            logger.info('Could not fetch config file: %s' % (response))
            exit('Exiting program.\n')

    else:
        logger.info('Config file prefix tells program to search ' +
                    'for it on filesystem.')

        if not os.path.isfile(config_file):
            exit('Config file doesn\'t exist on ' +
                 'filesystem: %s\n' % (config_file))

        ciphertext = open(config_file, 'rb').read()

    content = opencrypt.decrypt_file(
        ciphertext, write_to_file=False, is_ciphertext=True)
    try:
        config = json.loads(content)
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

    if not usm.get('templates'):
        logger.info('No `templates` field has been specified in config.')
        exit(1)

    for template in usm['templates']:
        if not(template.get('filename') or (template.get('title') and
               template.get('description'))):
            logger.info('`filename` or `title, description` fields are '
                        'required in each template.')

        if template.get('title') and template.get('description'):
            continue

        if template['filename'].startswith(('http', 'https', 'ftp')):
            logger.info('Fetching template file: %s' % (template['filename']))
            response = requests.get(template['filename'])

            if response.status_code < 400:
                content = response.content
            else:
                logger.info('Could not fetch config file: %s' % (response))
                exit('Exiting program.\n')

        else:
            if template['filename'] and not os.path.isfile(
                    template['filename']):
                logger.info('Template filename could not be found: '
                            '%s' % (template['filename']))
                exit(1)
            else:
                content = open(template['filename'], 'r').read()

        try:
            template_content = json.loads(content)
            template.update(template_content)
        except json.JSONDecodeError:
            logger.info('Could not parse template file: %s',
                        template['filename'])
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
    logger.info('Retrieving OAUTH token for USM...')
    res = requests.post(url, data={'grant_type': 'client_credentials'},
                        auth=(usm.get('client_id'), usm.get('client_secret')))

    if res.status_code < 300:
        return res.json().get('access_token')

    logger.info('Unexpected response returned: %s', res)
    return None


def get_usm_alarms(config, token):

    usm = config['usm']
    curr_time = str(time.time()).replace('.', str())[:13]
    prev_time = str(int(curr_time) - (usm.get('interval', 10) * 60 * 1000))
    params = ['sort=timestamp_occured,desc',
              'timestamp_occured_gte=' + prev_time]

    url = urljoin(usm.get('api_url'), 'alarms?%s' % ('&'.join(params)))
    logger.info('Retrieving USM alarms...')
    res = requests.get(url, headers={'Authorization': 'Bearer ' + token})
    if res.status_code < 300:
        alarms = res.json().get('_embedded', dict()).get('alarms', list())
        if not alarms:
            logger.info('USM has no alarms in given interval. '
                        'Exiting program.')
            exit(0)

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

        if not projects:
            logger.info('JIRA has no projects. Exiting program.')
            exit(1)

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
        issuetypes = list()
        for value in res.json():
            issuetypes.append({
                key: value for (key, value) in value.items()
                if key in query['fields']
            })

        if not issuetypes:
            logger.info('JIRA has no issue types. Exiting program.')
            exit(1)

        logger.info('[%d] issue types fetched from JIRA.', len(issuetypes))
        logger.info(str())
        return issuetypes

    logger.info('Unexpected response returned: %s', res)
    return None


def get_jira_issues(config):

    jira = config['jira']
    url = urljoin(jira.get('api_url'), 'search')
    logger.info('Retrieving JIRA issues...')

    if not(jira.get('project_key') and jira.get('interval')):
        logger.info('JIRA project and/or interval for issues are '
                    'missing in config. Only the latest 100 issues '
                    'will be considered.')

    query = dict()
    query['maxResults'] = 200
    query['fields'] = ['assignee', 'summary',
                       'description', 'created', 'updated']
    if jira.get('project_key') or jira.get('interval'):
        jql = list()
        jql.append('project = %s' % (jira['project_key'])
                   if jira.get('project_key') else str())
        jql.append('created > -%sm' % (jira['interval'])
                   if jira.get('interval') else str())

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
                'issue/%s/properties/_data' % issue.get('id'))

            res = requests.get(url, auth=(
                jira.get('username'), jira.get('api_token')))

            if res.status_code < 300 and res.json().get('value'):
                issue['properties'] = res.json().get('value')

        return issues

    logger.info('Unexpected response returned: %s', res.json())
    return list()


def filter_alarms(alarms, issues, config):

    filtered = list()
    usm = config['usm']
    if not usm.get('templates'):
        logger.info('No alarm templates specified in config. '
                    'Skipping all alarms...')
        return filtered

    posted_uuids = [x['properties']['alarm-uuid'] for x in issues if x.get(
                    'properties', dict()).get('alarm-uuid')]
    for alarm in alarms:
        if alarm['uuid'] in posted_uuids:
            continue

        is_triggered = False
        for template in usm['templates']:

            if isinstance(template.get('triggers'), dict):
                for key, value in template.get('triggers').items():
                    if key in alarm and value.strip(
                            '*').lower() in alarm[key].lower():
                        is_triggered = True

            if isinstance(template.get('triggers'), list):
                triggers = template.get('triggers', list())
                if alarm.get('rule_strategy') in triggers or \
                        alarm.get('rule_method') in triggers:
                    is_triggered = True

        if is_triggered:
            filtered.append(alarm)

    if not filtered:
        logger.info('No alarms to push to JIRA after '
                    'filtering. Exiting program.')
        exit(0)

    logger.info('[%d] alarms remained after filtering.', len(filtered))
    return filtered


def tickets_from_alarms(alarms, config):

    tickets = list()
    usm = config['usm']

    for alarm in alarms:
        ticket = dict()

        ticket['_uuid'] = alarm['uuid']
        ticket['_timestamp'] = alarm['timestamp_occured_iso8601']
        ticket['_priority'] = alarm['priority_label']
        ticket['_sources'] = alarm.get('alarm_source_names', list())
        ticket['_dests'] = alarm.get('alarm_destination_names', list())
        ticket['_sensor'] = alarm.get('alarm_sensor_sources').pop()

        ticket['SensorName'] = ''.join([
            usm.get('sensors', dict()).get(x, str())
            for x in usm.get('sensors', list())
            if x == ticket['_sensor']]) or 'Unknown'
        ticket['Date'] = ticket['_timestamp'][2:10].replace('-', str())
        ticket.update(alarm)
        tickets.append(ticket)

    for ticket in tickets:
        ticket_template = dict()
        for template in usm.get('templates'):
            if ticket['rule_strategy'] in template.get('triggers') or \
                    ticket['rule_method'] in template.get('triggers'):
                ticket_template = template.copy()
                break

        if not ticket_template:
            continue

        for key in ticket:
            if key.startswith('_'):
                continue

            if key in ticket_template.get('title'):
                if isinstance(ticket[key], list):
                    ticket[key] = ', '.join(ticket[key])
                ticket_template['title'] = ticket_template['title'] \
                    .replace('$%s' % (key), str(ticket[key]))

            if not ticket_template.get('description'):
                continue

            for idx, desc in enumerate(ticket_template['description']):
                if key in desc:
                    if isinstance(ticket[key], list):
                        ticket[key] = ', '.join(ticket[key])
                    desc = desc.replace('$%s' % (key), str(ticket[key]))
                    ticket_template['description'][idx] = desc

        for idx, desc in enumerate(ticket_template['description']):
            for variable in re.findall(r'(\$[\w-]*)', desc):
                desc = desc.replace(variable, 'unknown')
                ticket_template['description'][idx] = desc

        ticket['template'] = ticket_template
    return tickets


def filter_duplicate_tickets(issues, tickets):

    filtered = list()
    posted_md5s = [x['properties']['alarm-md5'] for x in issues if x.get(
        'properties', dict()).get('alarm-md5')]

    for ticket in tickets:
        template_hash = hashlib.md5(json.dumps({
            x: y for x, y in ticket['template'].items()
            if x in ['title', 'description']}).encode('utf8')).hexdigest()

        if template_hash not in posted_md5s:
            filtered.append(ticket)

    if not filtered:
        logger.info('No tickets to push to JIRA after pruning '
                    'duplicates. Exiting program.')
        exit(0)

    logger.info('[%d] tickets remained after '
                'removing duplicates.', len(filtered))
    return filtered


def push_tickets(tickets, projects, issue_types, config):

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

    data = {
        'fields': {
            'summary': '{title}',
            'project': {'id': '{project_id}'},
            'issuetype': {'id': '{issuetype_id}'},
            'description': '{description}'
        }
    }
    logger.info('Pushing tickets to JIRA...')
    responses = list()
    count = 0

    for ticket in tickets:

        url = urljoin(jira.get('api_url'), 'issue')
        ticket_data = json.dumps(data)

        ticket_data = ticket_data \
            .replace('{title}', ticket['template']['title']) \
            .replace('{description}', '\\n\\n'.join(
                ticket['template']['description'])) \
            .replace('{project_id}', project_id) \
            .replace('{issuetype_id}', issuetype_id) \

        ticket_data = json.loads(ticket_data)
        res = requests.post(url, json=ticket_data, auth=(
            jira.get('username'), jira.get('api_token')))

        if res.status_code >= 300:
            responses.append({
                'alarm_id': ticket['_uuid'],
                'ticket': '%s - %s' % (
                    ticket['rule_strategy'], ticket['rule_method']),
                'response': {
                    'code': res.status_code,
                    'content': res.content.decode('utf8')
                }
            })
            continue

        responses.append({
            'alarm_id': ticket['_uuid'],
            'ticket': '%s - %s' % (
                ticket['rule_strategy'], ticket['rule_method']),
            'response': res.json()
        })
        count += 1
        res = res.json()
        url = urljoin(
            jira.get('api_url'),
            'issue/%s/properties/_data' % (res.get('id')))

        template_hash = hashlib.md5(json.dumps({
            x: y for x, y in ticket['template'].items()
            if x in ['title', 'description']}).encode('utf8')).hexdigest()
        requests.put(
            url, json={
                'alarm-uuid': ticket.get('_uuid'),
                'alarm-md5': template_hash
            }, auth=(jira.get('username'), jira.get('api_token')))

    logger.info('[%d/%d] tickets pushed to JIRA successfully.',
                count, len(tickets))
    logger.info(str())
    return responses


def alert_on_slack(data, config):

    if not config.get('slack', dict()).get('webhooks'):
        logger.info('No webhook is specified. Skipping slack push.')
        return

    categories = {'success': list(), 'erred': list()}
    for entry in data:
        if entry.get('response', dict()).get('key'):
            categories['success'].append(entry)
        if entry.get('response', dict()).get('code'):
            categories['erred'].append(entry)

    prepared_string = config.get('slack', dict()).get('prefix', str()) + '\n'
    prepared_string += '*[%d/%d]* tickets pushed to JIRA ' \
        'successfully.\n' % (len(categories['success']), len(data))

    for entry in categories['success']:
        prepared_string += '> *`%s`* %s\n' % (
            entry['response']['key'], entry['ticket'])
    for entry in categories['erred']:
        prepared_string += '> *`Push failed [code: %s]`* %s)\n' % (
            entry['response']['code'], entry['ticket'])

    for url in config['slack']['webhooks']:
        response, _count = (None, 0)
        while not response and _count < 5:
            try:
                response = requests.post(url, json={
                    'text': prepared_string})
            except:
                logger.info('Could not send slack request. ' +
                            'Retrying after 10 secs...')
                time.sleep(10)
                _count += 1

        if not response:
            continue

        if response.status_code == 200:
            logger.info('Pushed message to slack successfully.')
        else:
            logger.info('Could not push message to slack: <(%s) %s>' % (
                response.status_code, response.content.decode('utf8')))
