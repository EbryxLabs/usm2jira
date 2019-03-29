# Introduction
usm2jira is a tool written in python to automate push of AlientVault's USM alarms to JIRA tickets. Using a central `.json` file as config, you can control different features of the program. `cf-template.yml` is also provided to automate deployment using **`AWS Cloudformation`**.

Confguration file in `.json` format is given in encrypted form and program decrypts it using AES keys provided in environment. For more information on encryption / decryption, look at [**opencrypt**](https://pypi.org/project/opencrypt/) library of python.


## Configuration
Program expects three subsections in your `.json` file as follows.
```
"usm": {...},
"jira": {...},
"slack": {...}
```
As you can guess, each section defines options for respective tools i.e. **USM**, **JIRA** and **Slack**.

### USM Options
For USM's API authentication, you should provide the api url for your hosted USM, client id and secret.
```
"usm": {
  "api_url": "https://<hosted-USM-REST-url>",
  "client_id": "<your-USM-client-id>",
  "client_secret": "<your-USM-client-secret>",
  ...
}
```
You can specify the interval in minutes to fetch all alarms after that timestamp. For example, an interval of 10 will fetch all USM alarms in last 10 mins.
```
"usm": {"interval": 100, ...}
```
You can provide sensors ids to map them against the names of sensors. Unfortunately, USM REST API doesn't provide the sensor names along with alarms data and there's no other way to fetch sensor names from USM. Hence, provide the ids in configuration as follows.
```
"usm": {
  "sensors": {
    "uuid-1": "name-1",
    "uuid-2": "name-2",
    ...
  },
  ...
}
```
Lastly, you have to provide one or more templates that will be used to post that to JIRA. Each template has **`triggers`**, **`title`** and **`description`** sub fields.
```
"usm": {
  "templates": [
    {
      "triggers": ["<USM-alarm-title>", "<USM-alarm-subtitle>", ...],
      "title": "$SensorName - High - $AlarmTitle ($SubCategory) [$Date]",
      "description": [
        "*Sensor:* $SensorName",
        "*Alarm:* $AlarmTitle",
        "*Infected Host:* $PrivateIP",
        "*External IP:* $PublicIP",
        "*Risk:* High",
        "*Description:*\\n A sample description.",
        "*Actions & Remediation:*\\n \\n- Step.1 \\n- Step.2"
      ]
    },
    ...
  ],
  ...
}
```
Keywords starting with `$` sign are variables that are populated using the data from USM. For example, `$SensorName` will be computed to `name-1` if an alert against that sensor was detected. **`title`** and **`description`** fields are used to layout JIRA tickets as you like. **`triggers`** can be used to detect only certain alarms from USM. Each alarm in USM has a title and a sub-title associated with it. You can specify title, sub-title or both and filter out rest of the alarms.

> Remember that we use **`interval`** field to filter out alarms for last N minutes as well.


### JIRA Options
Just like USM, you have to provide authentication details for JIRA's REST API.
```
"jira": {
  "api_url": "https://<your-JIRA-REST-url>",
  "username": "<your-username>",
  "api_token": "<your-api-token>",
  ...
}
```
Also provide JIRA's project you want to push the tickets to and type of ticket / issue you want them in.
```
"jira": {
  "project_key": "<project-key>",
  "issue_type": "story",
  ...
}
```
> Issue types other than `story` are not tested. Use them at your own risk.

You can also provide an interval which will be used to check whether there is a ticket/issue with same content already present in that timeslot. For example, an interval of 10 will check all tickets/issues created in last 10 minutes and if the tickets/issues to push from USM are already present, new tickets will not be created.
```
"jira": {"interval": 100, ...}
```
>Duplicates of USM alarms in JIRA are checked using alarms uuid which are inserted into JIRA issues as invisible properties. USM can create multiple alarms for a bruteforce attempt from same source and hence JIRA can have a lot of tickets for each redundant alarm. To avoid that, program checks the hash of tickets content and if hash matches to any previous ticket, new tickets are not created.


### Slack Options
You can specify webhooks for slack and program will alert you if any new ticket on JIRA has been created.
```
"slack": {
  "webhooks": [
    "https://<hook-url>",
    ...
  ]
}
```