from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import uvicorn
from rag.rag_engine import LogRageEngine
from typing import Optional, List
import jwt
import datetime
import hashlib
import random
import time
from passlib.context import CryptContext
import uuid
import boto3
from boto3.dynamodb.conditions import Key

from database import (
    init_dynamodb, get_users_table, get_keys_table, get_incidents_table, get_logs_table,
    store_log, get_logs, update_reliability_score, get_reliability_score, store_deployment, get_latest_deployment,
    store_chat_message, get_chat_sessions, get_chat_session_messages
)
import notifications
from predictive_engine import PredictiveEngine

# Initialize Predictive Engine
predictive_engine = PredictiveEngine()

# Initialize tables if they don't exist
try:
    init_dynamodb()
except Exception as e:
    print("Warning: Could not initialize DynamoDB tables (are AWS credentials set?):", e)

app = FastAPI(
    title="NexusAI SaaS API",
    description="Multi-tenant SaaS API with DynamoDB Backend",
    version="3.0.0"
)

engine = LogRageEngine()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

JWT_SECRET = "super_secret_jwt_key_for_nexus_saas"

def get_password_hash(password: str) -> str:
    # Use pure SHA-256 to absolutely guarantee no passlib 72-byte length crashes
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return hashlib.sha256(plain_password.encode('utf-8')).hexdigest() == hashed_password

# --- Models ---
class UserAuth(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = None
    otp_code: Optional[str] = None

class OTPRequest(BaseModel):
    email: str
    full_name: str

# In-memory OTP store: {email: {"otp": "123456", "full_name": "John", "expires": timestamp}}
otp_store: dict = {}

class ChatRequest(BaseModel):
    query: str
    time_window_mins: Optional[int] = 30
    image_base64: Optional[str] = None
    session_id: Optional[str] = None
    session_title: Optional[str] = None

class ChatResponse(BaseModel):
    answer: str
    citations: list

class ApiKeyResponse(BaseModel):
    key: str
    name: str

# --- OTP Endpoint ---
@app.post("/api/request-otp")
def request_otp(req: OTPRequest):
    """Generate and email a 6-digit OTP for email verification."""
    # Check if email already registered
    users_table = get_users_table()
    existing = users_table.get_item(Key={'email': req.email})
    if 'Item' in existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    otp_code = str(random.randint(100000, 999999))
    otp_store[req.email] = {
        "otp": otp_code,
        "full_name": req.full_name,
        "expires": time.time() + 120  # 2-minute TTL
    }

    # Send OTP email
    notifications.send_otp_email(
        email=req.email,
        full_name=req.full_name,
        otp_code=otp_code
    )
    return {"message": f"OTP sent to {req.email}. Please check your inbox."}

# --- Auth Endpoints (DynamoDB) ---
@app.post("/api/register")
def register_user(user: UserAuth):
    try:
        # Validate OTP first
        if not user.otp_code:
            raise HTTPException(status_code=400, detail="OTP code is required")

        stored = otp_store.get(user.email)
        if not stored:
            raise HTTPException(status_code=400, detail="No OTP found for this email. Please request one first.")
        if time.time() > stored["expires"]:
            del otp_store[user.email]
            raise HTTPException(status_code=400, detail="OTP expired. Please request a new one.")
        if stored["otp"] != user.otp_code:
            raise HTTPException(status_code=400, detail="Invalid OTP code.")

        full_name = user.full_name or stored.get("full_name", "")
        # Clear OTP after successful validation
        del otp_store[user.email]

        users_table = get_users_table()
        
        # Check if user exists
        response = users_table.get_item(Key={'email': user.email})
        if 'Item' in response:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        hashed_password = get_password_hash(user.password)
        user_id = str(uuid.uuid4())

        # Save user with full_name
        users_table.put_item(Item={
            'email': user.email,
            'user_id': user_id,
            'full_name': full_name,
            'hashed_password': hashed_password,
            'created_at': datetime.datetime.utcnow().isoformat()
        })
        
        # Generate default API key
        keys_table = get_keys_table()
        default_key = "nx_live_" + str(uuid.uuid4()).replace("-", "")
        keys_table.put_item(Item={
            'api_key': default_key,
            'user_id': user_id,
            'email': user.email,
            'name': "Default Integration Key",
            'is_active': True,
            'created_at': datetime.datetime.utcnow().isoformat()
        })
        
        return {"message": "User registered successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database Error: {str(e)}")

@app.post("/api/login")
def login_user(user: UserAuth):
    try:
        users_table = get_users_table()
        response = users_table.get_item(Key={'email': user.email})
        
        if 'Item' not in response:
            raise HTTPException(status_code=401, detail="Invalid credentials")
            
        db_user = response['Item']
        if not verify_password(user.password, db_user['hashed_password']):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        token = jwt.encode({
            "user_id": db_user['user_id'],
            "email": db_user['email'],
            "full_name": db_user.get('full_name', ''),
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, JWT_SECRET, algorithm="HS256")
        
        return {"token": token}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database Error: {str(e)}")

# --- Protected API Key Endpoints (DynamoDB) ---
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
        return payload  # Contains user_id and email
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.get("/api/keys", response_model=List[ApiKeyResponse])
def get_api_keys(current_user: dict = Depends(get_current_user)):
    keys_table = get_keys_table()
    user_id = current_user.get("user_id")
    
    response = keys_table.query(
        IndexName='UserIdIndex',
        KeyConditionExpression=Key('user_id').eq(user_id)
    )
    
    keys = response.get('Items', [])
    return [{"key": k['api_key'], "name": k.get('name', 'Key')} for k in keys if k.get('is_active', True)]

@app.post("/api/keys/generate", response_model=ApiKeyResponse)
def generate_api_key(current_user: dict = Depends(get_current_user)):
    keys_table = get_keys_table()
    new_key_str = "nx_live_" + str(uuid.uuid4()).replace("-", "")
    key_name = f"Key {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
    
    keys_table.put_item(Item={
        'api_key': new_key_str,
        'user_id': current_user.get("user_id"),
        'email': current_user.get("email"),
        'name': key_name,
        'is_active': True,
        'created_at': datetime.datetime.utcnow().isoformat()
    })
    
    return {"key": new_key_str, "name": key_name}

# --- Core Bot Endpoint (Secured via API Key in DynamoDB) ---
def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    api_key = credentials.credentials
    keys_table = get_keys_table()
    
    response = keys_table.get_item(Key={'api_key': api_key})
    if 'Item' not in response or not response['Item'].get('is_active', True):
        raise HTTPException(status_code=401, detail="Invalid or revoked API Key")
        
    return response['Item']

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, current_user: dict = Depends(get_current_user)):
    try:
        tenant_id = current_user.get("user_id")
        
        session_id = request.session_id or f"session_{uuid.uuid4().hex}"
        session_title = request.session_title or (request.query[:40] + ("..." if len(request.query) > 40 else ""))
        
        # Save user message to history
        store_chat_message(
            tenant_id=tenant_id,
            session_id=session_id,
            session_title=session_title,
            role="user",
            content=request.query,
            image_base64=request.image_base64
        )
        
        result = engine.run_query(
            query=request.query,
            time_window_mins=request.time_window_mins,
            image_base64=request.image_base64
        )
        
        answer = result.get("answer", "")
        
        # Save assistant response to history
        store_chat_message(
            tenant_id=tenant_id,
            session_id=session_id,
            session_title=session_title,
            role="assistant",
            content=answer
        )
        
        return ChatResponse(
            answer=answer,
            citations=result.get("citations", [])
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/chat/sessions")
def get_chat_sessions_endpoint(current_user: dict = Depends(get_current_user)):
    try:
        tenant_id = current_user.get("user_id")
        return get_chat_sessions(tenant_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/chat/sessions/{session_id}")
def get_chat_session_messages_endpoint(session_id: str, current_user: dict = Depends(get_current_user)):
    try:
        tenant_id = current_user.get("user_id")
        return get_chat_session_messages(tenant_id, session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Telemetry Ingress Models ---
class NexusEvent(BaseModel):
    service: str
    level: str
    message: str
    latency_ms: Optional[float] = None
    status_code: Optional[int] = None
    request_id: Optional[str] = None
    cluster_id: Optional[str] = None
    resource_id: Optional[str] = None

class GitHubDeploymentEvent(BaseModel):
    commit_sha: str
    commit_msg: str
    author: str
    repository: str
    workflow_run_id: Optional[str] = None
    pr_url: Optional[str] = None

@app.post("/api/v1/github/webhook")
def github_webhook(event: GitHubDeploymentEvent, current_user: dict = Depends(get_current_user)):
    """Receives GitHub Deployment and Workflow Run details for telemetry correlation."""
    try:
        tenant_id = current_user.get("user_id")
        timestamp = datetime.datetime.utcnow().isoformat() + "Z"
        
        success = store_deployment(
            tenant_id=tenant_id,
            timestamp=timestamp,
            deploy_data={
                "commit_sha": event.commit_sha,
                "commit_msg": event.commit_msg,
                "author": event.author,
                "repository": event.repository,
                "workflow_run_id": event.workflow_run_id,
                "pr_url": event.pr_url
            }
        )
        if not success:
            raise HTTPException(status_code=500, detail="Failed to store deployment correlation context")

        # Ingest a system log indicating a deployment occurred
        store_log(
            tenant_id=tenant_id,
            timestamp=timestamp,
            log_data={
                "service": "github-actions",
                "level": "INFO",
                "message": f"Deployment Completed: {event.repository} (Commit: {event.commit_sha[:7]} by {event.author})",
                "cluster_id": "github",
                "resource_id": event.workflow_run_id
            }
        )
        return {"status": "success", "message": "GitHub deployment recorded"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/ingest")
def ingest_telemetry(event: NexusEvent, current_user: dict = Depends(get_current_user)):
    try:
        tenant_id = current_user.get("user_id")
        tenant_email = current_user.get("email")
        timestamp = datetime.datetime.utcnow().isoformat() + "Z"
        
        # Abstraction Layer Log Write (Future proofed repository pattern)
        store_log(
            tenant_id=tenant_id,
            timestamp=timestamp,
            log_data={
                "service": event.service,
                "level": event.level,
                "message": event.message,
                "latency_ms": event.latency_ms,
                "status_code": event.status_code,
                "request_id": event.request_id,
                "cluster_id": event.cluster_id,
                "resource_id": event.resource_id
            }
        )
        
        is_reactive = event.level.upper() in ["ERROR", "CRITICAL", "FATAL"]

        if is_reactive:
            # --- 1. Reactive Pipeline ---
            # Update Reliability Score (Deduct 5.0 points)
            current_score = get_reliability_score(tenant_email)
            update_reliability_score(tenant_email, current_score - 5.0)

            incident_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
            incidents_table = get_incidents_table()
            incidents_table.put_item(Item={
                'tenant_id': tenant_id,
                'incident_id': incident_id,
                'status': 'OPEN',
                'severity': event.level.upper(),
                'service': event.service,
                'created_at': timestamp,
                'rca_report': ''
            })
            
            # Dispatch email using the Notification Framework
            notifications.notify_incident_created(
                tenant_email=tenant_email,
                incident_id=incident_id,
                service=event.service,
                severity=event.level.upper(),
                full_name=current_user.get("full_name", "")
            )
        else:
            # --- 2. Predictive Pipeline ---
            # Fetch recent logs for analyzing trends
            recent_logs = get_logs(tenant_id, limit=50)
            
            # Evaluate using predictive heuristics
            is_anomaly, prediction = predictive_engine.analyze_logs_and_predict(recent_logs)
            if is_anomaly and prediction:
                # Update Reliability Score (Deduct 2.0 points for proactive threat)
                current_score = get_reliability_score(tenant_email)
                update_reliability_score(tenant_email, current_score - 2.0)

                # Correlate with recent GitHub Deployment
                latest_deploy = get_latest_deployment(tenant_id)

                # Generate AI-assisted Predictive RCA
                rca_details = predictive_engine.generate_predictive_rca(prediction, latest_deploy)
                
                # Combine predictive alerts & trigger notification
                notifications.notify_predictive_alert(
                    tenant_email=tenant_email,
                    service=prediction["service"],
                    failure_type=prediction["failure_type"],
                    risk_score=prediction["risk_score"],
                    confidence_score=prediction["confidence_score"],
                    probable_cause=rca_details["probable_cause"],
                    suggested_remediation=rca_details["suggested_remediation"],
                    deployment_context=latest_deploy,
                    full_name=current_user.get("full_name", "")
                )
            
        return {"status": "success", "message": "Log ingested and processed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingest Error: {str(e)}")

@app.get("/api/v1/reliability")
def get_reliability(current_user: dict = Depends(get_current_user)):
    """Retrieves the current reliability score for the tenant."""
    try:
        tenant_email = current_user.get("email")
        score = get_reliability_score(tenant_email)
        return {"reliability_score": score}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/logs")
def get_logs(current_user: dict = Depends(get_current_user)):
    try:
        tenant_id = current_user.get("user_id")
        logs_table = get_logs_table()
        
        response = logs_table.query(
            KeyConditionExpression=Key('tenant_id').eq(tenant_id),
            ScanIndexForward=False, # Get newest first
            Limit=50
        )
        return response.get('Items', [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Incident Management ---
@app.get("/api/v1/incidents")
def get_incidents(current_user: dict = Depends(get_current_user)):
    try:
        tenant_id = current_user.get("user_id")
        incidents_table = get_incidents_table()
        
        response = incidents_table.query(
            KeyConditionExpression=Key('tenant_id').eq(tenant_id)
        )
        return response.get('Items', [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/incidents/{incident_id}/rca")
def generate_incident_rca(incident_id: str, current_user: dict = Depends(get_current_user)):
    try:
        tenant_id = current_user.get("user_id")
        incidents_table = get_incidents_table()
        
        # Verify incident belongs to tenant
        response = incidents_table.get_item(Key={'tenant_id': tenant_id, 'incident_id': incident_id})
        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Incident not found")
            
        incident = response['Item']
        
        # Trigger actual RCA generation (using the RAG engine)
        rca_query = f"Generate a Root Cause Analysis for incident {incident_id} affecting {incident.get('service')}. Look for recent errors in the logs."
        rca_result = engine.run_query(rca_query, time_window_mins=60)
        rca_report = rca_result.get("answer", "No RCA could be generated.")
        
        # Update Database
        incidents_table.update_item(
            Key={'tenant_id': tenant_id, 'incident_id': incident_id},
            UpdateExpression="SET rca_report = :rca, #st = :st",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={":rca": rca_report, ":st": "ANALYZED"}
        )
        
        # Send RCA Email
        notifications.notify_rca_completed(
            tenant_email=current_user.get("email"),
            incident_id=incident_id,
            service=incident.get("service"),
            rca_report=rca_report
        )
        
        return {"status": "success", "incident_id": incident_id, "rca_report": rca_report}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/github/deployments")
def get_github_deployments(current_user: dict = Depends(get_current_user)):
    """Retrieves deployment logs for the authenticated tenant."""
    try:
        tenant_id = current_user.get("user_id")
        table = get_deployments_table()
        response = table.query(
            KeyConditionExpression=Key('tenant_id').eq(tenant_id),
            ScanIndexForward=False,
            Limit=50
        )
        return response.get('Items', [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/k8s/resources")
def get_k8s_resources(current_user: dict = Depends(get_current_user)):
    """Returns cluster nodes, active pods, and deployment states for AKS/EKS dashboard visualization."""
    try:
        # Mock telemetry matching Kubernetes schema specifications
        return {
            "cluster_id": "aks-prod-cluster-01",
            "provider": "Azure Kubernetes Service",
            "region": "us-east-1",
            "nodes": [
                {"name": "aks-nodepool1-vm-0", "status": "Ready", "cpu_util": "48%", "mem_util": "62%"},
                {"name": "aks-nodepool1-vm-1", "status": "Ready", "cpu_util": "35%", "mem_util": "50%"},
                {"name": "aks-nodepool1-vm-2", "status": "Ready", "cpu_util": "72%", "mem_util": "85%"}
            ],
            "pods": [
                {"name": "payment-api-cf7d685-z8a9s", "namespace": "production", "status": "Running", "restarts": 0, "cpu": "120m", "mem": "240Mi"},
                {"name": "auth-service-5421c9b-h2n3s", "namespace": "production", "status": "Running", "restarts": 2, "cpu": "80m", "mem": "150Mi"},
                {"name": "log-collector-flb-8h1n2", "namespace": "kube-system", "status": "Running", "restarts": 0, "cpu": "50m", "mem": "95Mi"},
                {"name": "notification-worker-6b998-f2nsd", "namespace": "production", "status": "Running", "restarts": 1, "cpu": "110m", "mem": "180Mi"}
            ],
            "deployments": [
                {"name": "payment-api", "desired": 3, "ready": 3, "updated": 3},
                {"name": "auth-service", "desired": 2, "ready": 2, "updated": 2},
                {"name": "notification-worker", "desired": 2, "ready": 2, "updated": 2}
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/metrics")
def get_service_metrics(current_user: dict = Depends(get_current_user)):
    """Compiles service-specific telemetry indicators."""
    try:
        tenant_id = current_user.get("user_id")
        logs = get_logs(tenant_id, limit=100)
        
        # Aggregate heuristics per service
        metrics = {}
        for log in logs:
            srv = log.get("service", "unknown")
            if srv not in metrics:
                metrics[srv] = {"latency_sum": 0.0, "latency_count": 0, "warnings": 0, "errors": 0}
            
            lvl = log.get("level", "INFO").upper()
            if lvl == "WARN":
                metrics[srv]["warnings"] += 1
            elif lvl in ("ERROR", "CRITICAL", "FATAL"):
                metrics[srv]["errors"] += 1
                
            lat = log.get("latency_ms")
            if lat:
                metrics[srv]["latency_sum"] += float(lat)
                metrics[srv]["latency_count"] += 1
                
        results = []
        for srv, stats in metrics.items():
            avg_lat = stats["latency_sum"] / stats["latency_count"] if stats["latency_count"] > 0 else 0.0
            results.append({
                "service": srv,
                "avg_latency": round(avg_lat, 2),
                "warnings": stats["warnings"],
                "errors": stats["errors"],
                "health_score": max(0, 100 - (stats["errors"] * 10 + stats["warnings"] * 3))
            })
            
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# In-memory SaaS Connection store
integrations_store = {}

class ConnectionRequest(BaseModel):
    service: str # "github", "eks", or "aks"
    connected: bool
    credentials: Optional[dict] = None

@app.get("/api/v1/integrations")
def get_integrations(current_user: dict = Depends(get_current_user)):
    """Retrieves external integration statuses for this tenant workspace."""
    try:
        tenant_id = current_user.get("user_id")
        if tenant_id not in integrations_store:
            integrations_store[tenant_id] = {"github": False, "eks": False, "aks": False}
        return integrations_store[tenant_id]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/integrations/connect")
def update_integration_connection(req: ConnectionRequest, current_user: dict = Depends(get_current_user)):
    """Updates / Saves credentials and toggles connection status for an external service."""
    try:
        tenant_id = current_user.get("user_id")
        if tenant_id not in integrations_store:
            integrations_store[tenant_id] = {"github": False, "eks": False, "aks": False}
        
        service_key = req.service.lower()
        if service_key in integrations_store[tenant_id]:
            integrations_store[tenant_id][service_key] = req.connected
            return {"status": "success", "message": f"{req.service} connection status updated", "integrations": integrations_store[tenant_id]}
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported service integration: {req.service}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
