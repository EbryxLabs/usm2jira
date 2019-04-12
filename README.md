# Introduction
usm2jira is a tool written in python to automate push of AlientVault's USM alarms to JIRA tickets. Using a central `.json` file as config, you can control different features of the program. `cf-template.yml` is also provided to automate deployment using **`AWS Cloudformation`**.

Confguration file in `.json` format is given in encrypted form and program decrypts it using AES keys provided in environment. For more information on encryption / decryption, look at [**opencrypt**](https://pypi.org/project/opencrypt/) library of python.

## AWS Lambda Deployment
Create a deployment package, place it to S3 so you can specify it in your cloudformation process. You need make an archive containing all the required libraries as mentioned in `requirements.txt` file and python scripts containing the code.
```
cd /path/to/env/lib/pythonx.x/site-packages/
zip -r9 <archive-name> *
```
From root directory of the project, add python scripts to the same archive you created above:
```
zip -g <archive-name> setup.py script.py
zip -g <archive-name> usm2jira/*py
```
`script.main` is the invoker function for AWS Lambda. Otherwise, you can run locally by typing:
```
python script.py
```

## Configuration
Program expects three subsections in your `.json` file as follows.
```
"usm": {...},
"jira": {...},
"slack": {...}
```
As you can guess, each section defines options for respective tools i.e. **USM**, **JIRA** and **Slack**.

## USM Options
For USM's API authentication, you should provide the api url for your hosted USM, client id and secret.
```
"usm": {
  "api_url": "https://<hosted-USM-REST-url>/api/2.0/",
  "client_id": "<your-USM-client-id>",
  "client_secret": "<your-USM-client-secret>",
  ...
}
```
You can specify the interval in minutes to fetch all alarms after that timestamp. For example, an interval of 10 will fetch all USM alarms in last 10 mins.
```
"usm": {"interval": 100, ...}
```
You can provide sensors ids to map them against the names of sensors. Unfortunately, USM REST API doesn't provide the sensor names along with alarms data and there's no other way to fetch sensor names from USM.  
You can detect the sensor ids from `Data Sources > Sensors` page of your USM dashboad. Using the html source code of that page, provide the ids in configuration as follows.
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
Lastly, you have to provide one or more templates that will be used to post that to JIRA. Each template has **`triggers`** which are compared against alarm titles and subcategories returned from USM REST api. You can either have **`title`** and **`description`** for each template or **`filename`** field specifying template as an external file.
```
"usm": {
  "templates": [
    {
      "triggers": ["<USM-alarm-title>", "<USM-alarm-subtitle>", ...],
      "filename": "./my-sample-template.json"
    }, {
      "triggers": {
        "app_type": "cloudflare",
        "rule_intent": "Delivery & Attack",
        "rule_strategy": "WebServer Attack",
        "rule_name": "CF WAF Action Drop*"
      },
      "filename": "./my-sample-template-2.json"
    }
    ...
  ],
  ...
}
```
**`triggers`** can be used to detect only certain alarms from USM. Each alarm in USM has a title and a sub-title associated with it. You can specify title, sub-title or both and filter out rest of the alarms. Moreover, you can specify `app_type`, `rule_intent`, `rule_strategy` and `rule_name` in **`triggers`** instead of alarm title / subtitle. These fields can be fetched from USM alarm response returned from REST API.  
External template files can be placed locally or over the internet. Make sure to specify the correct url, and check accessibility, if template file is on internet.  
`my-sample-template.json` which is given above as external template file has to follow a json format:
```
{
  "title": "$SensorName - High - $rule_strategy ($rule_method) [$Date]",
  "description": [
    "*Sensor:* $SensorName",
    "*Alarm:* $rule_strategy",
    "*Infected Host:* $alarm_source_names",
    "*External IP:* $alarm_destination_names",
    "*Risk:* High",
    "*Description:*\\n A sample description.",
    "*Actions & Remediation:*\\n \\n- Step.1 \\n- Step.2"
  ]
}
```

Keywords starting with `$` sign are variables that are populated using the data from USM. **`title`** and **`description`** fields are used to layout JIRA tickets as you like.

> Remember that we use **`interval`** field to filter out alarms for last N minutes as well.

### Template variables
You can use any variable in template of your choice and if it's not detected in alarm response of USM, it will be replaced by `unknown` keyword. Program maps the keys from USM response to template variables. For example, if an alarm response has a field `rule_strategy` and template file specifies `$rule_strategy`, program will compute the value from USM.  
`$SensorName` and `$Date` are computed by program itself and independent of USM response fields.

#### Nested Fields
Consider the following response from USM.
```
{
  "uuid": "some-id-here",
  "name": "some-name-here",
  "targets": ["ip-1", "ip-2", "ip-3"],
  "sources": {
    "service": [{
      "name": "service-name",
      "ip": "service-ip"
    },
    ...
    ]
  }
}
```
You can use `$fieldName` for outer fields. e.g. `$uuid` will compute the id for alarm. For nested values and accessing certain items of an iterable use JSON notation.  
`$targets[1]` will give you second element i.e. `ip-2`.  
`$sources.service[0].name` will compute to `service-name`.
### USM Alarm Response
You can manually call your USM REST API and check the alarm response or you could use a ready-made bash function to quickly look over alarm response.
```
$: source usm2jira/get_alarm.curl
$: get_usm_alarm <api-url>/api/2.0/ <client-id> <client-secret> <alarm-uuid>
```

## JIRA Options
Just like USM, you have to provide authentication details for JIRA's REST API.
```
"jira": {
  "api_url": "https://<your-JIRA-REST-url>/rest/api/2/",
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


## Slack Options
You can specify webhooks for slack and program will alert you if any new ticket on JIRA has been created.
```
"slack": {
  "webhooks": [
    "https://<hook-url>",
    ...
  ]
}
```