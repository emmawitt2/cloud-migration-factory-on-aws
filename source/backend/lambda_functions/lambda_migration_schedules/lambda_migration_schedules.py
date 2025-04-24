#  Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#  SPDX-License-Identifier: Apache-2.0

import os
import json
import uuid
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError
from decimal import Decimal

from cmf_logger import logger, log_event_received
import cmf_boto
from cmf_utils import cors, default_http_headers

application = os.environ['application']
environment = os.environ['environment']

migration_schedules_table_name = '{}-{}-migration-schedules'.format(application, environment)
apps_table_name = '{}-{}-apps'.format(application, environment)
waves_table_name = '{}-{}-waves'.format(application, environment)

migration_schedules_table = cmf_boto.resource('dynamodb').Table(migration_schedules_table_name)
apps_table = cmf_boto.resource('dynamodb').Table(apps_table_name)
waves_table = cmf_boto.resource('dynamodb').Table(waves_table_name)

PREFIX_INVOCATION = 'Invocation:'
SUFFIX_DOESNT_EXIST = 'does not exist'


def lambda_handler(event, _):
    logging_context = 'migration-schedules:' + event['httpMethod']
    log_event_received(event)
    logger.debug(f'{PREFIX_INVOCATION} {logging_context}')

    if event['httpMethod'] == 'GET':
        return process_get(event, logging_context)
    elif event['httpMethod'] == 'POST':
        return process_post(event, logging_context)
    elif event['httpMethod'] == 'PUT':
        return process_put(event, logging_context)
    elif event['httpMethod'] == 'DELETE':
        return process_delete(event, logging_context)
    else:
        msg = 'Unsupported method: ' + event['httpMethod']
        logger.error(f'{PREFIX_INVOCATION} {logging_context}, {msg}')
        return {'headers': {**default_http_headers},
                'statusCode': 400, 'body': json.dumps({'errors': [msg]})}


def process_get(event, logging_context):
    # Check if we're getting a specific schedule or all schedules
    if 'migrationId' in event['pathParameters'] and event['pathParameters']['migrationId']:
        migration_id = event['pathParameters']['migrationId']
        try:
            resp = migration_schedules_table.get_item(Key={'migration_id': migration_id})
            if 'Item' in resp:
                # Get application details
                app_id = resp['Item']['application_id']
                app_resp = apps_table.get_item(Key={'app_id': app_id})
                if 'Item' in app_resp:
                    resp['Item']['application_name'] = app_resp['Item'].get('app_name', 'Unknown')
                
                # Get wave details
                if 'wave_id' in resp['Item']:
                    wave_id = resp['Item']['wave_id']
                    wave_resp = waves_table.get_item(Key={'wave_id': wave_id})
                    if 'Item' in wave_resp:
                        resp['Item']['wave_name'] = wave_resp['Item'].get('wave_name', 'Unknown')
                
                return {'headers': {**default_http_headers},
                        'body': json.dumps(resp['Item'], cls=JsonEncoder)}
            else:
                msg = f'Migration schedule with ID {migration_id} {SUFFIX_DOESNT_EXIST}'
                logger.error(f'{PREFIX_INVOCATION} {logging_context}, {msg}')
                return {'headers': {**default_http_headers},
                        'statusCode': 404, 'body': json.dumps({'errors': [msg]})}
        except Exception as e:
            logger.error(f'{PREFIX_INVOCATION} {logging_context}, Error getting migration schedule: {str(e)}')
            return {'headers': {**default_http_headers},
                    'statusCode': 500, 'body': json.dumps({'errors': [str(e)]})}
    else:
        # Get all schedules
        try:
            resp = migration_schedules_table.scan()
            items = resp['Items']
            
            # Get application and wave details for each schedule
            for item in items:
                app_id = item['application_id']
                app_resp = apps_table.get_item(Key={'app_id': app_id})
                if 'Item' in app_resp:
                    item['application_name'] = app_resp['Item'].get('app_name', 'Unknown')
                
                if 'wave_id' in item:
                    wave_id = item['wave_id']
                    wave_resp = waves_table.get_item(Key={'wave_id': wave_id})
                    if 'Item' in wave_resp:
                        item['wave_name'] = wave_resp['Item'].get('wave_name', 'Unknown')
            
            return {'headers': {**default_http_headers},
                    'body': json.dumps(items, cls=JsonEncoder)}
        except Exception as e:
            logger.error(f'{PREFIX_INVOCATION} {logging_context}, Error getting migration schedules: {str(e)}')
            return {'headers': {**default_http_headers},
                    'statusCode': 500, 'body': json.dumps({'errors': [str(e)]})}


def process_post(event, logging_context):
    try:
        body = json.loads(event['body'])
        
        # Validate required fields
        if 'application_id' not in body:
            msg = 'application_id is required'
            logger.error(f'{PREFIX_INVOCATION} {logging_context}, {msg}')
            return {'headers': {**default_http_headers},
                    'statusCode': 400, 'body': json.dumps({'errors': [msg]})}
        
        if 'scheduled_date' not in body:
            msg = 'scheduled_date is required'
            logger.error(f'{PREFIX_INVOCATION} {logging_context}, {msg}')
            return {'headers': {**default_http_headers},
                    'statusCode': 400, 'body': json.dumps({'errors': [msg]})}
        
        # Verify application exists
        app_resp = apps_table.get_item(Key={'app_id': body['application_id']})
        if 'Item' not in app_resp:
            msg = f'Application with ID {body["application_id"]} {SUFFIX_DOESNT_EXIST}'
            logger.error(f'{PREFIX_INVOCATION} {logging_context}, {msg}')
            return {'headers': {**default_http_headers},
                    'statusCode': 400, 'body': json.dumps({'errors': [msg]})}
        
        # Verify wave exists if provided
        if 'wave_id' in body and body['wave_id']:
            wave_resp = waves_table.get_item(Key={'wave_id': body['wave_id']})
            if 'Item' not in wave_resp:
                msg = f'Wave with ID {body["wave_id"]} {SUFFIX_DOESNT_EXIST}'
                logger.error(f'{PREFIX_INVOCATION} {logging_context}, {msg}')
                return {'headers': {**default_http_headers},
                        'statusCode': 400, 'body': json.dumps({'errors': [msg]})}
        
        # Generate a new migration_id
        migration_id = str(uuid.uuid4())
        
        # Set default status if not provided
        if 'status' not in body or not body['status']:
            body['status'] = 'Scheduled'
        
        # Add audit information
        now = datetime.now(timezone.utc).isoformat()
        username = get_username_from_event(event)
        
        # Create the new item
        new_item = {
            'migration_id': migration_id,
            'application_id': body['application_id'],
            'scheduled_date': body['scheduled_date'],
            'status': body['status'],
            'created_by': username,
            'last_updated': now
        }
        
        # Add optional fields if present
        if 'wave_id' in body and body['wave_id']:
            new_item['wave_id'] = body['wave_id']
        
        # Save to DynamoDB
        migration_schedules_table.put_item(Item=new_item)
        
        # Return the created item
        return {'headers': {**default_http_headers},
                'statusCode': 201,
                'body': json.dumps(new_item, cls=JsonEncoder)}
    
    except Exception as e:
        logger.error(f'{PREFIX_INVOCATION} {logging_context}, Error creating migration schedule: {str(e)}')
        return {'headers': {**default_http_headers},
                'statusCode': 500, 'body': json.dumps({'errors': [str(e)]})}


def process_put(event, logging_context):
    try:
        migration_id = event['pathParameters']['migrationId']
        body = json.loads(event['body'])
        
        # Check if the schedule exists
        resp = migration_schedules_table.get_item(Key={'migration_id': migration_id})
        if 'Item' not in resp:
            msg = f'Migration schedule with ID {migration_id} {SUFFIX_DOESNT_EXIST}'
            logger.error(f'{PREFIX_INVOCATION} {logging_context}, {msg}')
            return {'headers': {**default_http_headers},
                    'statusCode': 404, 'body': json.dumps({'errors': [msg]})}
        
        existing_item = resp['Item']
        
        # Verify application exists if changing
        if 'application_id' in body and body['application_id'] != existing_item['application_id']:
            app_resp = apps_table.get_item(Key={'app_id': body['application_id']})
            if 'Item' not in app_resp:
                msg = f'Application with ID {body["application_id"]} {SUFFIX_DOESNT_EXIST}'
                logger.error(f'{PREFIX_INVOCATION} {logging_context}, {msg}')
                return {'headers': {**default_http_headers},
                        'statusCode': 400, 'body': json.dumps({'errors': [msg]})}
        
        # Verify wave exists if changing
        if 'wave_id' in body and body['wave_id'] and (
                'wave_id' not in existing_item or body['wave_id'] != existing_item.get('wave_id')):
            wave_resp = waves_table.get_item(Key={'wave_id': body['wave_id']})
            if 'Item' not in wave_resp:
                msg = f'Wave with ID {body["wave_id"]} {SUFFIX_DOESNT_EXIST}'
                logger.error(f'{PREFIX_INVOCATION} {logging_context}, {msg}')
                return {'headers': {**default_http_headers},
                        'statusCode': 400, 'body': json.dumps({'errors': [msg]})}
        
        # Update audit information
        now = datetime.now(timezone.utc).isoformat()
        username = get_username_from_event(event)
        
        # Update the item with new values
        update_expression = "SET last_updated = :last_updated"
        expression_attribute_values = {
            ":last_updated": now
        }
        
        # Add fields to update
        if 'application_id' in body:
            update_expression += ", application_id = :application_id"
            expression_attribute_values[":application_id"] = body['application_id']
        
        if 'scheduled_date' in body:
            update_expression += ", scheduled_date = :scheduled_date"
            expression_attribute_values[":scheduled_date"] = body['scheduled_date']
        
        if 'status' in body:
            update_expression += ", status = :status"
            expression_attribute_values[":status"] = body['status']
        
        if 'wave_id' in body:
            if body['wave_id']:
                update_expression += ", wave_id = :wave_id"
                expression_attribute_values[":wave_id"] = body['wave_id']
            else:
                # Remove wave_id if empty
                update_expression += " REMOVE wave_id"
        
        # Update the item
        resp = migration_schedules_table.update_item(
            Key={'migration_id': migration_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues="ALL_NEW"
        )
        
        # Return the updated item
        return {'headers': {**default_http_headers},
                'body': json.dumps(resp['Attributes'], cls=JsonEncoder)}
    
    except Exception as e:
        logger.error(f'{PREFIX_INVOCATION} {logging_context}, Error updating migration schedule: {str(e)}')
        return {'headers': {**default_http_headers},
                'statusCode': 500, 'body': json.dumps({'errors': [str(e)]})}


def process_delete(event, logging_context):
    try:
        migration_id = event['pathParameters']['migrationId']
        
        # Check if the schedule exists
        resp = migration_schedules_table.get_item(Key={'migration_id': migration_id})
        if 'Item' not in resp:
            msg = f'Migration schedule with ID {migration_id} {SUFFIX_DOESNT_EXIST}'
            logger.error(f'{PREFIX_INVOCATION} {logging_context}, {msg}')
            return {'headers': {**default_http_headers},
                    'statusCode': 404, 'body': json.dumps({'errors': [msg]})}
        
        # Delete the item
        migration_schedules_table.delete_item(Key={'migration_id': migration_id})
        
        return {'headers': {**default_http_headers},
                'statusCode': 200,
                'body': json.dumps({'message': 'Migration schedule deleted successfully'})}
    
    except Exception as e:
        logger.error(f'{PREFIX_INVOCATION} {logging_context}, Error deleting migration schedule: {str(e)}')
        return {'headers': {**default_http_headers},
                'statusCode': 500, 'body': json.dumps({'errors': [str(e)]})}


def get_username_from_event(event):
    """Extract username from the event context if available"""
    try:
        if 'requestContext' in event and 'authorizer' in event['requestContext'] and 'claims' in event['requestContext']['authorizer']:
            return event['requestContext']['authorizer']['claims'].get('email', 'unknown')
    except Exception:
        pass
    return 'unknown'


class JsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        elif isinstance(obj, bytes):
            return str(obj, encoding='utf-8')
        return json.JSONEncoder.default(self, obj)
