import boto3
import os
import time
import datetime
import json
from typing import Optional

# Use the credentials and region configured in the environment
REGION = os.getenv("AWS_REGION", "us-east-1")
dynamodb = boto3.resource('dynamodb', region_name=REGION)

def init_dynamodb():
    """Auto-creates DynamoDB tables if they do not exist."""
    existing_tables = [table.name for table in dynamodb.tables.all()]
    
    if "NexusUsers" not in existing_tables:
        print("Creating NexusUsers DynamoDB table...")
        table = dynamodb.create_table(
            TableName='NexusUsers',
            KeySchema=[
                {'AttributeName': 'email', 'KeyType': 'HASH'}  # Partition key
            ],
            AttributeDefinitions=[
                {'AttributeName': 'email', 'AttributeType': 'S'}
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )
        table.wait_until_exists()
        print("NexusUsers table created successfully!")
 
    if "NexusApiKeys" not in existing_tables:
        print("Creating NexusApiKeys DynamoDB table...")
        table = dynamodb.create_table(
            TableName='NexusApiKeys',
            KeySchema=[
                {'AttributeName': 'api_key', 'KeyType': 'HASH'}  # Partition key
            ],
            AttributeDefinitions=[
                {'AttributeName': 'api_key', 'AttributeType': 'S'},
                {'AttributeName': 'user_id', 'AttributeType': 'S'}
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'UserIdIndex',
                    'KeySchema': [
                        {'AttributeName': 'user_id', 'KeyType': 'HASH'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {
                        'ReadCapacityUnits': 5,
                        'WriteCapacityUnits': 5
                    }
                }
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )
        table.wait_until_exists()
        print("NexusApiKeys table created successfully!")
 
    if "NexusIncidents" not in existing_tables:
        print("Creating NexusIncidents DynamoDB table...")
        table = dynamodb.create_table(
            TableName='NexusIncidents',
            KeySchema=[
                {'AttributeName': 'tenant_id', 'KeyType': 'HASH'},  # Partition key
                {'AttributeName': 'incident_id', 'KeyType': 'RANGE'} # Sort key
            ],
            AttributeDefinitions=[
                {'AttributeName': 'tenant_id', 'AttributeType': 'S'},
                {'AttributeName': 'incident_id', 'AttributeType': 'S'}
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )
        table.wait_until_exists()
        print("NexusIncidents table created successfully!")
 
    if "NexusLogs" not in existing_tables:
        print("Creating NexusLogs DynamoDB table...")
        table = dynamodb.create_table(
            TableName='NexusLogs',
            KeySchema=[
                {'AttributeName': 'tenant_id', 'KeyType': 'HASH'},  # Partition key
                {'AttributeName': 'timestamp', 'KeyType': 'RANGE'}  # Sort key
            ],
            AttributeDefinitions=[
                {'AttributeName': 'tenant_id', 'AttributeType': 'S'},
                {'AttributeName': 'timestamp', 'AttributeType': 'S'}
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )
        table.wait_until_exists()
        print("NexusLogs table created successfully!")
 
    if "NexusDeployments" not in existing_tables:
        print("Creating NexusDeployments DynamoDB table...")
        table = dynamodb.create_table(
            TableName='NexusDeployments',
            KeySchema=[
                {'AttributeName': 'tenant_id', 'KeyType': 'HASH'},  # Partition key
                {'AttributeName': 'timestamp', 'KeyType': 'RANGE'}  # Sort key
            ],
            AttributeDefinitions=[
                {'AttributeName': 'tenant_id', 'AttributeType': 'S'},
                {'AttributeName': 'timestamp', 'AttributeType': 'S'}
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )
        table.wait_until_exists()
        print("NexusDeployments table created successfully!")

    if "NexusChatHistory" not in existing_tables:
        print("Creating NexusChatHistory DynamoDB table...")
        table = dynamodb.create_table(
            TableName='NexusChatHistory',
            KeySchema=[
                {'AttributeName': 'tenant_id', 'KeyType': 'HASH'},  # Partition key
                {'AttributeName': 'timestamp', 'KeyType': 'RANGE'}  # Sort key
            ],
            AttributeDefinitions=[
                {'AttributeName': 'tenant_id', 'AttributeType': 'S'},
                {'AttributeName': 'timestamp', 'AttributeType': 'S'}
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )
        table.wait_until_exists()
        print("NexusChatHistory table created successfully!")

def get_users_table():
    return dynamodb.Table('NexusUsers')
 
def get_keys_table():
    return dynamodb.Table('NexusApiKeys')
 
def get_incidents_table():
    return dynamodb.Table('NexusIncidents')
 
def get_logs_table():
    return dynamodb.Table('NexusLogs')
 
def get_deployments_table():
    return dynamodb.Table('NexusDeployments')

def get_chat_history_table():
    return dynamodb.Table('NexusChatHistory')

# --- Log Storage Abstraction Layer (Repository Pattern) ---
def store_log(tenant_id: str, timestamp: str, log_data: dict) -> bool:
    """Stores a log entry using the decoupled repository layer."""
    try:
        table = get_logs_table()
        table.put_item(Item={
            'tenant_id': tenant_id,
            'timestamp': timestamp,
            'service': log_data.get('service', 'unknown'),
            'level': log_data.get('level', 'INFO'),
            'message': log_data.get('message', ''),
            'latency_ms': str(log_data.get('latency_ms')) if log_data.get('latency_ms') is not None else None,
            'status_code': log_data.get('status_code'),
            'request_id': log_data.get('request_id'),
            'cluster_id': log_data.get('cluster_id'),
            'resource_id': log_data.get('resource_id')
        })
        return True
    except Exception as e:
        print(f"Log Repository write failed: {e}")
        return False
 
def get_logs(tenant_id: str, limit: int = 50) -> list:
    """Retrieves logs using the decoupled repository layer."""
    try:
        table = get_logs_table()
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('tenant_id').eq(tenant_id),
            ScanIndexForward=False,
            Limit=limit
        )
        return response.get('Items', [])
    except Exception as e:
        print(f"Log Repository read failed: {e}")
        return []
 
# --- Reliability Score Integration ---
def update_reliability_score(email: str, score: float) -> bool:
    """Updates the user's/tenant's reliability score in their user profile."""
    try:
        table = get_users_table()
        # Ensure score is within valid bounds [0, 100]
        clamped_score = max(0.0, min(100.0, float(score)))
        table.update_item(
            Key={'email': email},
            UpdateExpression="SET reliability_score = :score",
            ExpressionAttributeValues={':score': str(clamped_score)}
        )
        return True
    except Exception as e:
        print(f"Failed to update reliability score for {email}: {e}")
        return False
 
def get_reliability_score(email: str) -> float:
    """Retrieves the reliability score for a given tenant email."""
    try:
        table = get_users_table()
        response = table.get_item(Key={'email': email})
        if 'Item' in response:
            return float(response['Item'].get('reliability_score', 100.0))
        return 100.0
    except Exception as e:
        print(f"Failed to fetch reliability score: {e}")
        return 100.0
 
def store_deployment(tenant_id: str, timestamp: str, deploy_data: dict) -> bool:
    """Stores GitHub deployment metadata for correlation."""
    try:
        table = get_deployments_table()
        table.put_item(Item={
            'tenant_id': tenant_id,
            'timestamp': timestamp,
            'commit_sha': deploy_data.get('commit_sha', 'unknown'),
            'commit_msg': deploy_data.get('commit_msg', ''),
            'author': deploy_data.get('author', ''),
            'repository': deploy_data.get('repository', ''),
            'workflow_run_id': deploy_data.get('workflow_run_id'),
            'pr_url': deploy_data.get('pr_url', '')
        })
        return True
    except Exception as e:
        print(f"Deployment storage failed: {e}")
        return False
 
def get_latest_deployment(tenant_id: str) -> Optional[dict]:
    """Retrieves the latest deployment for correlation."""
    try:
        table = get_deployments_table()
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('tenant_id').eq(tenant_id),
            ScanIndexForward=False, # Newest first
            Limit=1
        )
        items = response.get('Items', [])
        return items[0] if items else None
    except Exception as e:
        print(f"Failed to retrieve latest deployment: {e}")
        return None

# --- Chat History Management (with Local Fallback) ---
def store_chat_message(tenant_id: str, session_id: str, session_title: str, role: str, content: str, image_base64: Optional[str] = None) -> bool:
    """Saves a single message inside a specific chat session in the repository."""
    timestamp = datetime.datetime.utcnow().isoformat() + "Z"
    try:
        table = get_chat_history_table()
        table.put_item(Item={
            'tenant_id': tenant_id,
            'timestamp': timestamp,
            'session_id': session_id,
            'session_title': session_title,
            'role': role,
            'content': content,
            'image_base64': image_base64
        })
        return True
    except Exception as e:
        print(f"DynamoDB Chat History write failed: {e}. Falling back to local file.")
        
    try:
        local_path = "local_chat_history.json"
        history = []
        if os.path.exists(local_path):
            with open(local_path, "r") as f:
                history = json.load(f)
        history.append({
            'tenant_id': tenant_id,
            'timestamp': timestamp,
            'session_id': session_id,
            'session_title': session_title,
            'role': role,
            'content': content,
            'image_base64': image_base64
        })
        history = history[-500:] # Cap storage history size
        with open(local_path, "w") as f:
            json.dump(history, f, indent=2)
        return True
    except Exception as local_ex:
        print(f"Local Chat History write failed: {local_ex}")
        return False

def get_chat_sessions(tenant_id: str) -> list:
    """Aggregates and returns unique chat sessions with their latest titles and activity timestamps."""
    try:
        table = get_chat_history_table()
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('tenant_id').eq(tenant_id),
            ScanIndexForward=True
        )
        items = response.get('Items', [])
        return _group_messages_into_sessions(items)
    except Exception as e:
        print(f"DynamoDB Chat Sessions read failed: {e}. Falling back to local file.")
        
    try:
        local_path = "local_chat_history.json"
        if os.path.exists(local_path):
            with open(local_path, "r") as f:
                history = json.load(f)
            tenant_history = [msg for msg in history if msg.get('tenant_id') == tenant_id]
            return _group_messages_into_sessions(tenant_history)
        return []
    except Exception as local_ex:
        print(f"Local Chat Sessions read failed: {local_ex}")
        return []

def _group_messages_into_sessions(messages: list) -> list:
    sessions_dict = {}
    for msg in messages:
        sid = msg.get("session_id")
        if not sid:
            continue
        sessions_dict[sid] = {
            "session_id": sid,
            "session_title": msg.get("session_title") or "Unnamed Chat",
            "last_active": msg.get("timestamp")
        }
    sessions_list = list(sessions_dict.values())
    sessions_list.sort(key=lambda s: s["last_active"], reverse=True)
    return sessions_list

def get_chat_session_messages(tenant_id: str, session_id: str) -> list:
    """Retrieves all messages belonging to a specific session_id."""
    try:
        table = get_chat_history_table()
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('tenant_id').eq(tenant_id),
            FilterExpression=boto3.dynamodb.conditions.Attr('session_id').eq(session_id),
            ScanIndexForward=True
        )
        return response.get('Items', [])
    except Exception as e:
        print(f"DynamoDB Chat Messages read failed: {e}. Falling back to local file.")
        
    try:
        local_path = "local_chat_history.json"
        if os.path.exists(local_path):
            with open(local_path, "r") as f:
                history = json.load(f)
            return [msg for msg in history if msg.get('tenant_id') == tenant_id and msg.get('session_id') == session_id]
        return []
    except Exception as local_ex:
        print(f"Local Chat Messages read failed: {local_ex}")
        return []




