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
            model_kwargs={"temperature": 0.1}
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
            "CRITICAL: If the user's input is a greeting (e.g., 'hi', 'hello', 'hey') or general small talk, respond with a brief, friendly greeting and ask how you can assist them as an SRE helper. In this case, respond in a plain, natural conversational style. Do NOT use markdown headers (like ##), lists, empty incident analysis, or code snippets.\n\n"
            "Otherwise, for general technical queries or incident analysis, follow these rules:\n"
            "1. Analyze operational logs, traces, and system metrics to identify incident root causes.\n"
            "2. Answer any general questions related to DevOps, AI, development, deployment, and security.\n"
            "3. Act as a powerful automation tool: Write code, generate complete automation scripts, CI/CD pipelines, and infrastructure-as-code snippets when requested.\n"
            "4. Facilitate communication: If the user asks to 'send an email' or alert someone, provide the exact Python script (using smtplib or boto3 SES) or bash/curl command needed to automate that task immediately.\n"
            "5. **Interactive Diagram Generation**: If the user asks to draw, generate, design, or sketch an architecture diagram, you MUST output a valid JSON containing the diagram shapes inside a fenced code block marked with language 'excalidraw'.\n"
            "   The JSON schema structure MUST follow this exact pattern:\n"
            "   {{\n"
            "     \"type\": \"excalidraw\",\n"
            "     \"elements\": [\n"
            "       {{\n"
            "         \"id\": \"unique_id_1\",\n"
            "         \"type\": \"rectangle\",\n"
            "         \"x\": 100,\n"
            "         \"y\": 100,\n"
            "         \"width\": 150,\n"
            "         \"height\": 80,\n"
            "         \"strokeColor\": \"#4f46e5\",\n"
            "         \"backgroundColor\": \"#1e293b\",\n"
            "         \"fillStyle\": \"hachure\",\n"
            "         \"strokeWidth\": 2,\n"
            "         \"roughness\": 1\n"
            "       }},\n"
            "       {{\n"
            "         \"id\": \"unique_id_2\",\n"
            "         \"type\": \"text\",\n"
            "         \"x\": 110,\n"
            "         \"y\": 120,\n"
            "         \"text\": \"ALB Ingress\",\n"
            "         \"fontSize\": 16,\n"
            "         \"fontFamily\": 1\n"
            "       }},\n"
            "       {{\n"
            "         \"id\": \"unique_id_3\",\n"
            "         \"type\": \"arrow\",\n"
            "         \"x\": 175,\n"
            "         \"y\": 180,\n"
            "         \"points\": [[0,0], [0,80]],\n"
            "         \"strokeColor\": \"#fbbf24\",\n"
            "         \"strokeWidth\": 2,\n"
            "         \"roughness\": 1\n"
            "       }}\n"
            "     ]\n"
            "   }}\n"
            "   Draw 4-6 connected nodes (e.g. Route 53, Ingress, Pods, Databases) arranged neatly with clean vertical or horizontal offsets so shapes and arrows do not overlap.\n\n"
            "Format the response using professional markdown with headers, bullet points, and extensive code blocks where appropriate. "
            "Do NOT use simple placeholders; provide fully functional and robust code solutions. Localize all money mentions in Indian Rupees (₹).\n\n"
            "If the user is asking about an incident or analyzing logs, follow these strict troubleshooting guidelines:\n"
            "1. **Trace Correlation**: Look for matching `request_id` across different microservices. Correlate failures.\n"
            "2. **Outage Timeline**: Summarize the sequence of events.\n"
            "3. **Identified Cause**: State clearly which microservice is the root cause.\n"
            "4. **Recommendations & Automation**: Provide concrete operational steps AND the automated script/command to fix it immediately.\n"
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
