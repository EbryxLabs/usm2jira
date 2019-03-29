import json
from usm2jira import *


def main():

    config = read_config()
    token = get_auth_token(config)
    alarms = get_usm_alarms(config, token)

    issues = get_jira_issues(config)
    projects = get_jira_projects(config)
    issue_types = get_jira_issue_types(config)

    filtered_alarms = filter_alarms(alarms, issues, config)
    tickets = tickets_from_alarms(filtered_alarms, config)
    tickets = filter_duplicate_tickets(issues, tickets)
    responses = push_tickets(tickets, projects, issue_types, config)
    alert_on_slack(responses, config)
    print(json.dumps(responses, indent=2))


if __name__ == "__main__":
    main()
