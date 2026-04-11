import os
import uuid
import subprocess
import chromadb
import ollama 
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from ddgs import DDGS
from tavily import TavilyClient

# -------------------- Config --------------------
OLLAMA_IP = "localhost:8000"
MODEL_NAME = "gemma4:e4b"
CHROMA_DB_PATH = "./chroma_db"

TAVILY_API_KEY = "YOUR_API_KEY"
tavily = TavilyClient(api_key=TAVILY_API_KEY)

# Initialize the explicit client for network stability
client = ollama.Client(host=OLLAMA_IP)

# -------------------- FastAPI --------------------
app = FastAPI(title="Home AI Assistant (Gemma 4)")

frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "frontend"))
if os.path.exists(frontend_path):
    app.mount("/frontend", StaticFiles(directory=frontend_path, html=True), name="frontend")

# -------------------- ChromaDB --------------------
chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
memory_collection = chroma_client.get_or_create_collection(name="assistant_memory")

    
def web_search(query: str):
    """
    Advanced AI-optimized search for current events and deep information.
    """
    try:
        # search_depth="advanced" is slower but much better quality
        # include_answer=True gives you a pre-written AI summary
        response = tavily.search(
            query=query, 
            search_depth="basic", 
            max_results=2,
            include_answer=false
        )
        
        # 1. Start with Tavily's own AI-generated summary
        result_text = f"TAVILY SUMMARY: {response.get('answer', 'No summary available.')}\n\n"
        
        # 2. Add the specific snippets from the top 3 websites
        result_text += "TOP SOURCES:\n"
        for r in response.get('results', []):
            result_text += f"- Source: {r['url']}\n  Content: {r['content']}\n\n"
            
        return result_text
    except Exception as e:
        return f"Tavily Search error: {str(e)}"

def run_command(cmd: str):
    """
    Run a local system command for diagnostics. Allowed: ipconfig, ping, dir.
    Args:
        cmd: The exact system command to execute.
    """
    allowed_commands = ["ipconfig", "ping", "dir"]
    base_cmd = cmd.split()[0].lower()
    if base_cmd not in allowed_commands:
        return "❌ Command not allowed"
    try:
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT)
    except Exception as e:
        return f"Command error: {str(e)}"

# Mapping for the execution loop
available_tools = {
    "web_search": web_search,
    "run_command": run_command
}

# -------------------- Memory Context --------------------
def get_memory_context(query: str):
    try:
        results = memory_collection.query(query_texts=[query], n_results=2)
        docs = results.get("documents", [[]])[0]
        return "\n".join(docs) if docs else "No relevant past memory."
    except:
        return ""
import time

def get_system_time():
    """
    Get the exact current local time from the server system clock. 
    Use this instead of web search for the current time.
    """
    # This gets the time directly from your computer/server
    return time.strftime("%I:%M %p %Z")

# Add to your dictionary
available_tools["get_system_time"] = get_system_time


# -------------------- Agent Logic --------------------
def process_prompt(user_prompt: str):
    try:
        # Check connection before starting
        client.ps() 
    except Exception:
        return "❌ I can't reach the Ollama server. Check your network/IP settings."

    if len(user_prompt) > 20:
        memory = get_memory_context(user_prompt)
    
    memory = " "
    
    messages = [
        {
            "role": "system", 
            "content": f"You are a smart home assistant. Current date: April 7, 2026. Context: {memory}"
        },
        {"role": "user", "content": user_prompt}
    ]

    # 1. Ask model to generate a response or tool call
    response = client.chat(
        model=MODEL_NAME,
        messages=messages,
        tools=[web_search, run_command] 
    )

    # 2. Check if the model wants to use a tool
    if response.message.tool_calls:
        # Add assistant's intent to history
        messages.append(response.message) 

        for tool in response.message.tool_calls:
            function_name = tool.function.name
            args = tool.function.arguments
            
            print(f"Executing Tool: {function_name} with {args}")
            
            if function_name in available_tools:
                output = available_tools[function_name](**args)
            else:
                output = f"Error: Tool {function_name} not found."

            # Add tool result to conversation
            messages.append({
                'role': 'tool',
                'content': str(output),
                'name': function_name
            })

        # 3. Final call to synthesize the result
        final_response = client.chat(model=MODEL_NAME, messages=messages)
        return final_response.message.content

    return response.message.content

# -------------------- API Endpoint --------------------
class ChatRequest(BaseModel):
    prompt: str

@app.post("/chat")
def chat_endpoint(req: ChatRequest):
   
    try:
        result = process_prompt(req.prompt)
        
        # Save interaction to long-term memory
        memory_collection.add(
            ids=[str(uuid.uuid4())],
            documents=[f"User: {req.prompt}\nAssistant: {result}"]
        )
        return {"result": result}
    except Exception as e:
        return {"error": str(e)}
# import os
# import uuid
# import subprocess
# import chromadb
# from fastapi import FastAPI
# from fastapi.staticfiles import StaticFiles
# from pydantic import BaseModel
# from duckduckgo_search import DDGS # For free web search

# # -------------------- Config --------------------
# # Ollama library defaults to http://localhost:11434. 
# # Inside Docker, we point it to the host.
# os.environ["OLLAMA_HOST"] = "http://host.docker.internal:11434"
# CHROMA_DB_PATH = "./chroma_db"
# MODEL_NAME = "gemma4:latest" # Must be 3.1+ for tool calling


# import ollama  # Import official library
# # -------------------- FastAPI --------------------
# app = FastAPI(title="Home AI Assistant")

# frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "frontend"))
# if os.path.exists(frontend_path):
#     app.mount("/frontend", StaticFiles(directory=frontend_path, html=True), name="frontend")

# # -------------------- ChromaDB --------------------
# chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
# memory_collection = chroma_client.get_or_create_collection(name="assistant_memory")

# # -------------------- Real Tools (Functions) --------------------
# def web_search(query: str):
#     """
#     Search the web for current events, news, weather, or information after 2024.
#     """
#     try:
#         with DDGS() as ddgs:
#             results = [r['body'] for r in ddgs.text(query, max_results=3)]
#             return "\n".join(results) if results else "No results found."
#     except Exception as e:
#         return f"Search error: {str(e)}"

# def run_command(cmd: str):
#     """
#     Run a system command. Allowed: ipconfig, ping, dir.
#     """
#     allowed_commands = ["ipconfig", "ping", "dir"]
#     base_cmd = cmd.split()[0].lower()
#     if base_cmd not in allowed_commands:
#         return "❌ Command not allowed"
#     try:
#         return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT)
#     except Exception as e:
#         return f"Command error: {str(e)}"

# # Mapping for the model to use
# available_tools = {
#     "web_search": web_search,
#     "run_command": run_command
# }

# # -------------------- Memory --------------------
# def get_memory_context(query: str):
#     try:
#         results = memory_collection.query(query_texts=[query], n_results=2)
#         docs = results.get("documents", [[]])[0]
#         return "\n".join(docs) if docs else "No relevant past memory."
#     except:
#         return ""

# # -------------------- Agent Logic --------------------
# def process_prompt(user_prompt: str):
#     memory = get_memory_context(user_prompt)
    
#     messages = [
#         {"role": "system", "content": f"You are a smart home assistant. Current date: April 2, 2026. Past context: {memory}"},
#         {"role": "user", "content": user_prompt}
#     ]

#     # 1. Ask model to generate a response or tool call
#     response = ollama.chat(
#         model=MODEL_NAME,
#         messages=messages,
#         tools=[web_search, run_command] # Give it the function signatures
#     )

#     # 2. Check if the model wants to use a tool
#     if response.get('message', {}).get('tool_calls'):
#         messages.append(response['message']) # Add AI's intent to message history

#         for tool in response['message']['tool_calls']:
#             function_name = tool['function']['name']
#             args = tool['function']['arguments']
            
#             # Execute the actual Python function
#             print(f"Calling tool: {function_name} with {args}")
#             output = available_tools[function_name](**args)

#             # Add tool result to conversation
#             messages.append({
#                 'role': 'tool',
#                 'content': output,
#                 'name': function_name
#             })

#         # 3. Final call to synthesize the result
#         final_response = ollama.chat(model=MODEL_NAME, messages=messages)
#         return final_response['message']['content']

#     return response['message']['content']

# # -------------------- API --------------------
# class ChatRequest(BaseModel):
#     prompt: str

# @app.post("/chat")
# def chat_endpoint(req: ChatRequest):
#     try:
#         result = process_prompt(req.prompt)
#         memory_collection.add(
#             ids=[str(uuid.uuid4())],
#             documents=[f"User: {req.prompt}\nAssistant: {result}"]
#         )
#         return {"result": result}
#     except Exception as e:
#         return {"error": str(e)}
