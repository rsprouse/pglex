# pglex - A 'pretty good' lexical service

pglex is a 'pretty good' lexical service (pglex) designed to facilitate
the construction of dictionary websites and other applications that
incorporate lexical data. With pglex, researchers can provide lexical
entries in JSON format to an instance of the pglex API and get
‘pretty good’ search results without requiring language-specific
configurations.

To use pglex you create one or more [Elasticsearch](https://www.elastic.co/what-is/elasticsearch)
indexes for your language projects that contain lexical entries that use
predefined fields common to lexical entries. You can then use the pglex
API to query and retrieve your entries. The pglex API has built-in
defaults that make lexical queries simple to construct.

The code in this repository uses [Chalice](https://github.com/aws/chalice)
to create a serverless Python application on
[Amazon Web Services](https://aws.amazon.com/) (AWS). With some work it
could be adapted to another serverless framework or self-hosted setup.

## Using the pglex API

API queries are constructed by adding a project name and action to your
API endpoint and `POST`ing a query payload. For example, the `q` action is
used to search your lexical entries. If we want to search the entries of
the `karuk` project the query might look like:

`POST`
`https://0d687zto0h.execute-api.us-east-1.amazonaws.com/api/karuk/q`
JSON Payload: `{ "q": "salmon" }`

This query searches the lexical entries in the `karuk` Elasticsearch index
and returns a JSON object containing an array of search entries ranked
by relevance.

To retrieve one or more lexical entries by ID, use the `lex` action:

`POST`
`https://0d687zto0h.execute-api.us-east-1.amazonaws.com/api/karuk/lex`
JSON Payload: `{ "lexid": "[30,31]" }`

This action returns a JSON object containing a JSON dictionary of entries,
keyed by ID.

## Getting started with pglex

To get started with pglex, first clone the repository with:

```
git clone https://github.com/rsprouse/pglex
```

Every language project served by your pglex instance needs to be defined
to make it available in the API. To add a project, edit [`app.py`](chalice/app.py)
and update the `projects` dictionary. Each project needs to be a key in the
`projects` dictionary. Start by changing the name of `mylang` to your project
name. It's not necessary to make any other changes in order to get pretty good
results.

## Deploying on AWS

This section outlines the steps to deploy pglex on AWS. While these steps will
help you get started they are not a replacement for the AWS documentation.

***Deploying to AWS is not free.*** We have been running a small site
for a little less than $30 USD per month. Most of that amount is the
cost of running a single `t2.small.elasticsearch` virtual machine instance
in the `us-west-1` region for the Elasticsearch domain (approximately $27).
Costs for the API Gateway and Lambda services contribute smaller amounts
to the total. You can monitor your resource usage and costs in the
AWS Management Console.

### Set up a Python environment on your local machine

To ensure you have a working deployment environment it is desirable to install
specific package versions that are known to work with the pglex code and AWS
offerings. You can use the following command to create a working environment
in [Anaconda Python](https://www.anaconda.com/products/individual):

```
conda create --name pglex --channel conda-forge python=3.7.1 chalice=1.9.1 elasticsearch=6.3.1 elasticsearch-dsl=6.3.0 requests-aws4auth=0.9 awscli=1.16.132
```

This command creates an environment named `pglex` with dependencies known to
be compatible with pglex. It is possible that newer versions of these libraries
are also compatible, but these are untested.

### Log in to the AWS Management Console

To get started, log in to the
[AWS Management Console](https://console.aws.amazon.com).

After you log in, select an [AWS region](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.RegionsAndAvailabilityZones.html)
where you want to deploy pglex. Normally
you can see the current region in the upper right hand corner of the console.
Our example will use `us-west-1` (N. California), and you should select a
region appropriate for your needs.

### Set up IAM groups and users

First we create a group named `pglex_deploy` with policies attached to it that
are appropriate for deploying the pglex service. We also create a user named
`pglex_deployer` and add it to the `pflex_deploy` group.

#### Create the deployment group

1. Navigate to the Identity and Access Management (IAM) service.
1. Select 'Groups' from IAM sidebar.
1. Click on the 'Create new group' button.
1. For group name, use `pglex_deploy`.
1. Search for and select the following AWS Managed policies to attach to the group.
  - AWSLambdaFullAccess
  - AmazonAPIGatewayAdministrator
  - IAMFullAccess
1. Click the 'Create group' button to finish creating the group.

#### Create the deployment user

1. Select 'Users' from the IAM sidebar.
1. Click on the 'Add user' button.
1. For user name, use `pglex_deployer`.
1. For access type, select 'Programmatic access'.
1. To set permissions, add the user to the `pglex_deploy` group.
1. It is not necessary to add any tags.
1. Click the 'Create user' button to finish creating the group.
1. On the next screen, save the user credentials, as you will not have a second
chance to copy them. Either use the 'Download .csv' button to save the credentials
in a .csv file, or copy and paste the Access key ID and Secret access key to
a secure location. If you forget to do this step or lose the credentials you
can assign a new set of credentials for the `pglex_deployer` user at any time
in the IAM console.

### Store your AWS user credentials

The chalice command will look in the same [credentials file](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html)
as the AWS CLI does. Set up a profile for the `pglex_deployer` user in this
file. It will look something like this:

```
[pglex_deployer]
aws_access_key_id=<access key id>
aws_secret_access_key=<secret access key>
region=us-west-1
```

The access key id and secret access key values are the ones that you saved
when you created the `pglex_deployer` user.

You can test the `aws` command and `pglex_deployer` credentials with:

```
aws lambda list-layers --profile pglex_deployer
```

If you are new to AWS the response will look something like this:

```
{
    "Layers": []
}
```

If you receive an error message you will probably need to correct your
credentials file before moving on.

### Create an Elasticsearch domain

Before getting started with your Elasticsearch domain, grab the ARN of the
`pglex_depoyer` user. When creating the ES domain you will set a policy that
restricts access to the ES domain to this user.

1. Navigate to the IAM service.
1. Click 'Users' from the IAM sidebar.
1. Click on the `pglex_deployer` user name to view the user details.
1. Copy and save the User ARN value you find in the summary information. You will
use this value when creating an access policy for your ES domain.

To create your Elasticsearch domain navigate to the Elasticsearch service.

1. ES domains can be created in many different AWS regions. Make sure that
your console is set to the appropriate region before getting started.
1. Click on the 'Create a new domain' button.
1. Choose deployment type 'Development and testing'.
1. Choose Elasticsearch version 6.8. The pglex code might work with ES 7.x,
but this has not been tested.
1. For Elasticsearch domain name choose 'pglex'.
1. It is not necessary to enable a custom endpoint.
1. For the least expensive operation choose the smallest instance type,
t2.small.elasticsearch, and set the number of nodes to 1. AWS recommends more
redundancy (nodes) for production services, but in practice we have found this
minimal setup has been sufficient for our needs and has been reliable. If your
ES domain requires more resources you can increase the number and size of your
instances types easily in the management console.
1. For data node storage select type 'EBS', EBS volume type 'General purpose
(SSD)', and storage size per node '10' GiB.
1. Do not enable dedicated master nodes.
1. For network configuration choose 'Public access'. An access policy will
restrict access to the `pglex_deployer` user.
1. It is not necessary to enable fine-grained access control, SAML authentication
for Kibana, or Amazon Cognito authentication.
1. For access policy, choose 'Custom access policy' with the settings 'IAM ARN'
and 'Allow'. In the box with the 'Enter principal' prompt enter the ARN for the
`pglex_deployer` user.
1. For encryption select 'Require HTTPS for all traffic to the domain.
1. It is not necessary to add any tags.
1. Click 'Confirm' and wait for the domain status to become 'Active'.
1. Take note of the 'Endpoint' value for your ES domain. You will use it as
the `es_endpoint` value in the `config.json` file when you deploy the Chalice
app.

### Deploy the Chalice app

The Chalice application creates your API endpoints and routes requests to
Lambda functions that query your ES domain. Query results from ES are packed
by the function and returned to the client.

#### Create `config.json`

When you deploy the app the Chalice `config.json` file contains settings that
are pushed to AWS and used at runtime. Before deploying you must create this
file with appropriate values.

***WARNING: `config.json` will contain the secret access key for the
`pglex_deployer` user on AWS. Keep the contents of
this file secure, and do not add it to your github repo.***

Use this JSON template to create a file named `config.json` in
[chalice/.chalice](chalice/.chalice) and substitute appropriate values:

```
{
  "version": "2.0",
  "app_name": "pglex",
  "environment_variables": {
    "aws_access_key_id": "<pglex_deployer access key id here>",
    "aws_secret_access_key": "<pglex_deployer secret access key here",
    "aws_region": "<your aws region, e.g. us-west-1>",
    "es_endpoint": "<hostname for your es domain, e.g. pglex-somepath.us-west-1.es.amazonaws.com>"
  },
  "stages": {
    "dev": {
      "api_gateway_stage": "devapi",
      "environment_variables": {
        "cors_domain": "<hostname of your development app, e.g. linguistics.berkeley.edu>"
      }
    },
    "prod": {
      "api_gateway_stage": "api",
      "environment_variables": {
        "cors_domain": "<hostname of your production app, e.g. linguistics.berkeley.edu>"
      }
    }
  }
}
```

You can find the `es_endpoint` value by visiting the 'Overview' of the `pglex`
ES domain in the AWS Management Console. Use the hostname without the protocol
(https://).

You can deploy multiple versions of the API using stages. In our example there
are two stages for development and production versions of the API. The
`api_gateway_stage` value is a string that is appended to the AWS hostname as
part of the URL. Any environment variables that should have specific values
per-stage can be defined here instead of in the top-level `enrvironment_variables`
container. The `cors_domain` variable should be set to the hostname of the
server where your application that uses the API is located. For example, if
your online dictionary is at http://linguistics.berkeley.edu/~karuk, then
`linguistics.berkeley.edu` is an appropriate value.

Because the `.chalice` directory is named with a leading '.' your operating
system might treat it as hidden and make it difficult for you to find it.
If so you might need to change your view options to show hidden folders.

#### Deploy

To deploy, first make sure the Python environment where you installed the
pglex dependencies is active:

```
conda activate pglex
```

Then run `chalice deploy` from the [chalice](chalice) directory. In order
for the `chalice` command to use the correct AWS credentials you should
first set the `AWS_PROFILE` environment variable to the name of the
`pglex_deployer` profile in your AWS credentials file.

```
export AWS_PROFILE=pglex_deployer
cd chalice
chalice deploy
```

The result should look something like this:

```
Creating deployment package.
Creating IAM role: pglex-dev
Creating lambda function: pglex-dev
Creating Rest API
Resources deployed:
  - Lambda ARN: arn:aws:lambda:us-west-1:967992620111:function:pglex-dev
  - Rest API URL: https://o6avgt37eh.execute-api.us-west-1.amazonaws.com/devapi/
```

The `Rest API URL` is the base URL for your pglex API. Add your project
name and action to this URL, e.g.
`https://o6avgt37eh.execute-api.us-west-1.amazonaws.com/devapi/karuk/q`.

As you can see from the API URL, Chalice's default deployment stage is
"dev". To deploy the "prod" stage use the `--stage` parameter:

```
chalice deploy --stage prod
```

The result will contain the URL for the production API. Note that the
hostname is different for each stage.

You can retrieve the URL for a stage with:

```
chalice url --stage dev
```

or

```
chalice url --stage prod
```

To clean up and remove an API stage use:

```
chalice delete --stage dev
```

### Load JSON data

Now that your API is deployed you'll need some data loaded into Elasticsearch
for it to query.

The instructions you see below will not be easy to follow if you are unfamiliar
with Elasticsearch. The pglex roadmap includes plans for easier creation and
updating of project indexes.

Each language project has a separate ES index of lexical entries. The
name of each index uses the template: `lex_{project}_{version}-lex`, where
`{project}` is the name of a language project that you used as a key in the
`projects` dictionary in `app.py`. The `{version}` is a version identifier
that you can use to create separate indexes for development purposes. In
normal use you can ignore the version and use the default value of `1`, so an
example index name would be `lex_karuk_1-lex`.

The .json files in the [examples](examples) directory can be used as a model
for your indexes. The [`lex_karuk_1-lex-def.json`](examples/lex_karuk_1-lex-def.json)
file contains ES index settings for commonly-used fields of lexical entries.
Use the contents of this file as the payload for the ES index creation
command:

```
PUT lex_karuk_1-lex
{
  "settings": {
    ...
  }
}
```

See the [ES docs](https://www.elastic.co/guide/en/elasticsearch/reference/6.8/indices-create-index.html)
for more on creating indexes.

You can then use the `_bulk` endpoint to load data from the
[lex_karuk_1-lex_bulkdata.json](examples/lex_karuk_1-lex_bulkdata.json) file:

```
PUT lex_karuk_1-lex/_bulk
{ "index" : { "_index": "lex_karuk_1-lex", "_type": "lex", "_id" : "30" } }
{"is_morph": ... }
```

The `index` value must match the index name you just created.

See the [ES docs](https://www.elastic.co/guide/en/elasticsearch/reference/6.8/docs-bulk.html)
for more on bulk upload of data.
