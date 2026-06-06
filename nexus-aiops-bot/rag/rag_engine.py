import os
import json
import boto3
from langchain_aws import ChatBedrock, BedrockEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

class LogRageEngine:
    def __init__(self):
        aws_region = os.getenv("AWS_REGION", "us-east-1")
        bedrock_client = boto3.client("bedrock-runtime", region_name=aws_region)

        self.embeddings = BedrockEmbeddings(
            client=bedrock_client,
            model_id="amazon.titan-embed-text-v2:0"
        )
        self.chat_model = ChatBedrock(
            client=bedrock_client,
            model_id=os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"),
            model_kwargs={"temperature": 0.1, "max_tokens": 4096}
        )
        self.vector_store = None

    def run_query(self, query: str, time_window_mins: int = 30, image_base64: str = None) -> dict:
        """Runs vector search on log indexes and performs root cause analysis with Bedrock model."""

        retrieved_logs = []
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        local_logs_path = os.path.join(current_dir, "local_logs.json")
        if not os.path.exists(local_logs_path):
            local_logs_path = "local_logs.json"

        if os.path.exists(local_logs_path):
            try:
                with open(local_logs_path, "r") as f:
                    local_logs = json.load(f)
                if local_logs:
                    docs = [Document(page_content=json.dumps(log)) for log in local_logs]
                    if not self.vector_store:
                        self.vector_store = FAISS.from_documents(docs, self.embeddings)
                    results = self.vector_store.similarity_search(query, k=15)
                    retrieved_logs = [json.loads(d.page_content) for d in results]
            except Exception as e:
                return {
                    "answer": f"Retrieval Error: FAISS search failed. Details: {str(e)}",
                    "citations": []
                }

        if retrieved_logs:
            context_str = "\n".join([
                f"- [{log.get('timestamp', '')}] Service: {log.get('service', '')} | Level: {log.get('level', '')} | Message: {log.get('message', '')} "
                f"| Status: {log.get('status_code', '')} | Latency: {log.get('latency_ms', '')}ms | ReqID: {log.get('request_id', '')}"
                for log in retrieved_logs
            ])
        else:
            context_str = "No specific incident logs found for this query in the specified time window."

        system_prompt = (
            "You are an expert DevSecOps AI SRE Assistant and Automation Engineer.\n\n"
            "CRITICAL: If the user's input is a greeting (e.g., 'hi', 'hello', 'hey') or general small talk, "
            "respond with a brief, friendly greeting and ask how you can assist them as an SRE helper. "
            "In this case, respond in a plain, natural conversational style. Do NOT use markdown headers (like ##), "
            "lists, empty incident analysis, or code snippets.\n\n"
            "Otherwise, for general technical queries or incident analysis, follow these rules:\n"
            "1. Analyze operational logs, traces, and system metrics to identify incident root causes.\n"
            "2. Answer any general questions related to DevOps, AI, development, deployment, and security.\n"
            "3. Act as a powerful automation tool: Write code, generate complete automation scripts, CI/CD pipelines, "
            "and infrastructure-as-code snippets when requested.\n"
            "4. Facilitate communication: If the user asks to 'send an email' or alert someone, provide the exact "
            "Python script (using smtplib or boto3 SES) or bash/curl command needed to automate that task immediately.\n"
            "5. ARCHITECTURE DIAGRAM GENERATION: If the user asks to draw, generate, design, or sketch an architecture "
            "diagram, output valid JSON inside a fenced code block with language tag 'excalidraw'.\n\n"
            "   MANDATORY RULES FOR ALL DIAGRAMS:\n"
            "   - Use ONLY these element types: rectangle, ellipse, diamond, arrow, text, line. NEVER use type 'image'.\n"
            "   - ALWAYS set fontFamily to 3 on EVERY text element. fontFamily 3 = Cascadia Code (plain readable text). "
            "     fontFamily 1 or 2 renders icon glyphs instead of text — NEVER use them.\n"
            "   - ALWAYS set roughness to 0 on every element (clean straight lines, not hand-drawn).\n"
            "   - ALWAYS set strokeWidth to 2.\n"
            "   - ALWAYS set fillStyle to 'solid' on rectangles and ellipses.\n"
            "   - Every shape node (rectangle/ellipse) MUST have a separate 'text' element placed inside it, "
            "     containing only plain English words (e.g. 'Load Balancer', 'EKS Cluster', 'RDS DB'). "
            "     NEVER use emoji, Unicode icons, or special characters in text content.\n"
            "   - Arrows must have 'points' as an array of [x,y] pairs relative to the arrow's x,y origin.\n\n"
            "   COLOR PALETTE:\n"
            "   - Load Balancer/API Gateway: strokeColor '#8b5cf6', backgroundColor '#1e1b4b'\n"
            "   - Compute (EC2/EKS/VM/Pod):  strokeColor '#3b82f6', backgroundColor '#1e3a8a'\n"
            "   - Database (RDS/DynamoDB):   strokeColor '#10b981', backgroundColor '#064e3b'\n"
            "   - Queue/Messaging (SQS/SNS): strokeColor '#f59e0b', backgroundColor '#78350f'\n"
            "   - Storage/CDN (S3/CF):       strokeColor '#06b6d4', backgroundColor '#0c4a6e'\n"
            "   - VPC/Subnet bounding box:   strokeColor '#94a3b8', backgroundColor 'transparent', strokeStyle 'dashed'\n"
            "   - Arrows:                    strokeColor '#fbbf24'\n"
            "   - Text inside nodes:         strokeColor '#ffffff', backgroundColor 'transparent'\n\n"
            "   COMPLETE WORKING EXAMPLE — replicate this exact pattern:\n"
            "   ```excalidraw\n"
            "   {{\n"
            "     \"type\": \"excalidraw\",\n"
            "     \"elements\": [\n"
            "       {{\"id\":\"vpc\",\"type\":\"rectangle\",\"x\":20,\"y\":20,\"width\":740,\"height\":440,"
            "\"strokeColor\":\"#94a3b8\",\"backgroundColor\":\"transparent\",\"fillStyle\":\"solid\","
            "\"strokeWidth\":2,\"roughness\":0,\"strokeStyle\":\"dashed\",\"opacity\":80}},\n"
            "       {{\"id\":\"vpc_lbl\",\"type\":\"text\",\"x\":30,\"y\":28,\"width\":240,\"height\":18,"
            "\"text\":\"AWS VPC  10.0.0.0/16\",\"fontSize\":13,\"fontFamily\":3,"
            "\"strokeColor\":\"#94a3b8\",\"backgroundColor\":\"transparent\",\"roughness\":0}},\n"
            "       {{\"id\":\"alb\",\"type\":\"rectangle\",\"x\":60,\"y\":120,\"width\":160,\"height\":60,"
            "\"strokeColor\":\"#8b5cf6\",\"backgroundColor\":\"#1e1b4b\",\"fillStyle\":\"solid\","
            "\"strokeWidth\":2,\"roughness\":0}},\n"
            "       {{\"id\":\"alb_txt\",\"type\":\"text\",\"x\":60,\"y\":142,\"width\":160,\"height\":18,"
            "\"text\":\"ALB / Load Balancer\",\"fontSize\":13,\"fontFamily\":3,"
            "\"strokeColor\":\"#ffffff\",\"backgroundColor\":\"transparent\",\"roughness\":0,\"textAlign\":\"center\"}},\n"
            "       {{\"id\":\"eks\",\"type\":\"rectangle\",\"x\":320,\"y\":120,\"width\":160,\"height\":60,"
            "\"strokeColor\":\"#3b82f6\",\"backgroundColor\":\"#1e3a8a\",\"fillStyle\":\"solid\","
            "\"strokeWidth\":2,\"roughness\":0}},\n"
            "       {{\"id\":\"eks_txt\",\"type\":\"text\",\"x\":320,\"y\":142,\"width\":160,\"height\":18,"
            "\"text\":\"EKS Cluster\",\"fontSize\":13,\"fontFamily\":3,"
            "\"strokeColor\":\"#ffffff\",\"backgroundColor\":\"transparent\",\"roughness\":0,\"textAlign\":\"center\"}},\n"
            "       {{\"id\":\"rds\",\"type\":\"rectangle\",\"x\":320,\"y\":300,\"width\":160,\"height\":60,"
            "\"strokeColor\":\"#10b981\",\"backgroundColor\":\"#064e3b\",\"fillStyle\":\"solid\","
            "\"strokeWidth\":2,\"roughness\":0}},\n"
            "       {{\"id\":\"rds_txt\",\"type\":\"text\",\"x\":320,\"y\":322,\"width\":160,\"height\":18,"
            "\"text\":\"RDS PostgreSQL\",\"fontSize\":13,\"fontFamily\":3,"
            "\"strokeColor\":\"#ffffff\",\"backgroundColor\":\"transparent\",\"roughness\":0,\"textAlign\":\"center\"}},\n"
            "       {{\"id\":\"s3\",\"type\":\"rectangle\",\"x\":580,\"y\":120,\"width\":140,\"height\":60,"
            "\"strokeColor\":\"#06b6d4\",\"backgroundColor\":\"#0c4a6e\",\"fillStyle\":\"solid\","
            "\"strokeWidth\":2,\"roughness\":0}},\n"
            "       {{\"id\":\"s3_txt\",\"type\":\"text\",\"x\":580,\"y\":142,\"width\":140,\"height\":18,"
            "\"text\":\"S3 Bucket\",\"fontSize\":13,\"fontFamily\":3,"
            "\"strokeColor\":\"#ffffff\",\"backgroundColor\":\"transparent\",\"roughness\":0,\"textAlign\":\"center\"}},\n"
            "       {{\"id\":\"arr1\",\"type\":\"arrow\",\"x\":220,\"y\":150,\"width\":100,\"height\":0,"
            "\"points\":[[0,0],[100,0]],\"strokeColor\":\"#fbbf24\",\"strokeWidth\":2,\"roughness\":0,"
            "\"startArrowhead\":null,\"endArrowhead\":\"arrow\"}},\n"
            "       {{\"id\":\"arr1_lbl\",\"type\":\"text\",\"x\":244,\"y\":132,\"width\":60,\"height\":16,"
            "\"text\":\"HTTPS\",\"fontSize\":11,\"fontFamily\":3,\"strokeColor\":\"#fbbf24\","
            "\"backgroundColor\":\"transparent\",\"roughness\":0}},\n"
            "       {{\"id\":\"arr2\",\"type\":\"arrow\",\"x\":400,\"y\":180,\"width\":0,\"height\":120,"
            "\"points\":[[0,0],[0,120]],\"strokeColor\":\"#fbbf24\",\"strokeWidth\":2,\"roughness\":0,"
            "\"startArrowhead\":null,\"endArrowhead\":\"arrow\"}},\n"
            "       {{\"id\":\"arr2_lbl\",\"type\":\"text\",\"x\":410,\"y\":232,\"width\":70,\"height\":16,"
            "\"text\":\"SQL Query\",\"fontSize\":11,\"fontFamily\":3,\"strokeColor\":\"#fbbf24\","
            "\"backgroundColor\":\"transparent\",\"roughness\":0}},\n"
            "       {{\"id\":\"arr3\",\"type\":\"arrow\",\"x\":480,\"y\":150,\"width\":100,\"height\":0,"
            "\"points\":[[0,0],[100,0]],\"strokeColor\":\"#fbbf24\",\"strokeWidth\":2,\"roughness\":0,"
            "\"startArrowhead\":null,\"endArrowhead\":\"arrow\"}},\n"
            "       {{\"id\":\"arr3_lbl\",\"type\":\"text\",\"x\":500,\"y\":132,\"width\":60,\"height\":16,"
            "\"text\":\"PUT/GET\",\"fontSize\":11,\"fontFamily\":3,\"strokeColor\":\"#fbbf24\","
            "\"backgroundColor\":\"transparent\",\"roughness\":0}}\n"
            "     ]\n"
            "   }}\n"
            "   ```\n\n"
            "   Build a COMPLETE diagram with all components the user describes. Space nodes at least 80px apart. "
            "Place arrow label text 15px above the midpoint of each arrow. "
            "Bounding boxes (VPC/Subnet) must be large enough to contain all child nodes with 40px padding.\n\n"
            "Format the response using professional markdown with headers, bullet points, and extensive code blocks "
            "where appropriate. Do NOT use simple placeholders; provide fully functional and robust code solutions. "
            "Localize all money mentions in Indian Rupees (Rs.).\n\n"
            "If the user is asking about an incident or analyzing logs, follow these strict troubleshooting guidelines:\n"
            "1. **Trace Correlation**: Look for matching request_id across different microservices. Correlate failures.\n"
            "2. **Outage Timeline**: Summarize the sequence of events.\n"
            "3. **Identified Cause**: State clearly which microservice is the root cause.\n"
            "4. **Recommendations & Automation**: Provide concrete operational steps AND the automated script/command "
            "to fix it immediately.\n"
            "5. **Citations**: Mention the timestamps and services."
        )

        user_prompt = (
            "Here is the context representing the retrieved logs from FAISS Vector Store (if any):\n"
            "---CONTEXT START---\n"
            "{context}\n"
            "---CONTEXT END---\n\n"
            "Analyze these logs (if present) and answer the user query: \"{query}\""
        )

        from langchain_core.messages import SystemMessage, HumanMessage

        if image_base64:
            clean_b64 = image_base64
            if "," in image_base64:
                clean_b64 = image_base64.split(",")[1]
                
            formatted_user = user_prompt.format(context=context_str, query=query)
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=[
                    {"type": "text", "text": formatted_user},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{clean_b64}"
                        }
                    }
                ])
            ]
            chain = self.chat_model | StrOutputParser()
            try:
                answer = chain.invoke(messages)
            except Exception as chat_ex:
                answer = f"AI Vision Error: Could not generate diagram analysis. Details: {str(chat_ex)}"
        else:
            prompt_template = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("human", user_prompt)
            ])
            chain = prompt_template | self.chat_model | StrOutputParser()
            try:
                answer = chain.invoke({
                    "context": context_str,
                    "query": query
                })
            except Exception as chat_ex:
                answer = f"AI Error: Could not generate response. Details: {str(chat_ex)}"

        return {
            "answer": answer,
            "citations": retrieved_logs
        }
