# async_map_reduce.py
import os
import asyncio
import time
from typing import List, Dict, Any
from pydantic import BaseModel, Field
import instructor
from openai import AsyncOpenAI

# 1. Define Summary Schemas for the Reduce Phase
class FileSummary(BaseModel):
    filename: str
    exported_functions: List[str] = Field(description="Names of top-level functions found in this file.")
    core_purpose: str = Field(description="One-sentence high-level summary of what this module handles.")

class SystemArchitectureMap(BaseModel):
    total_files_processed: int
    system_overview: str = Field(description="A cohesive summary explaining how these files collaborate.")
    module_index: List[FileSummary]

# 2. Initialize the ASYNCHRONOUS Client for High-Throughput
# AsyncOpenAI allows us to fire concurrent non-blocking HTTP requests to Groq
async_client = instructor.from_openai(
    AsyncOpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ.get("GROQ_API_KEY")
    )
)

# 3. THE MAP FUNCTION: Processes a single file asynchronously
async def map_parse_file(filename: str, source_code: str) -> FileSummary:
    """Worker thread that analyzes an individual file concurrently without blocking others."""
    print(f"[Map Worker] 🚀 Started processing: {filename}")
    start_time = time.time()
    
    prompt = f"""
    Analyze the following source code module. Extract all major function names and 
    summarize its core architectural purpose in a single, clear sentence.
    
    Filename: {filename}
    Source Code:
    ```python
    {source_code}
    ```
    """
    
    # Non-blocking async API call
    response = await async_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        response_model=FileSummary,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1
    )
    
    elapsed = time.time() - start_time
    print(f"[Map Worker] ✅ Finished: {filename} in {elapsed:.2f}s")
    return response

# 4. THE REDUCE FUNCTION: Aggregates independent summaries into a unified map
async def reduce_summaries(summaries: List[FileSummary]) -> SystemArchitectureMap:
    """Compiles all independent map outputs into a singular, cohesive global structural index."""
    print(f"\n[Reduce Engine] 📥 Aggregating {len(summaries)} file summaries into global index...")
    
    # Convert summaries to string context
    serialized_context = "\n".join([
        f"File: {s.filename} | Functions: {s.exported_functions} | Purpose: {s.core_purpose}" 
        for s in summaries
    ])
    
    prompt = f"""
    You are the Lead Systems Architect. Review these independent file summaries from our repository 
    and output a unified global architecture map. Explain how these modules interact as a cohesive system.
    
    Module Summaries:
    {serialized_context}
    """
    
    response = await async_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        response_model=SystemArchitectureMap,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    return response

# 5. ORCHESTRATION LAYER: Simulating a Multi-File Repository
async def main():
    # Mocking an enterprise repository structure with multiple decoupled modules
    mock_repo = {
        "auth_service.py": "def login_user(u, p):\n    print('Checking credentials')\ndef logout_user(token):\n    print('Revoking token')",
        "billing_engine.py": "def calculate_taxes(subtotal):\n    return subtotal * 0.18\ndef charge_credit_card(user_id, amount):\n    print('Stripe charge executed')",
        "notification_router.py": "def send_transactional_sms(phone, text):\n    print('Twilio SMS sent')\ndef dispatch_welcome_email(email):\n    print('SES Email sent')"
    }
    
    print("⚡ Initializing Asynchronous Map-Reduce Pipeline...")
    global_start = time.time()
    
    # Step 1: Create async tasks for all files (The Map Scatter)
    tasks = [map_parse_file(fname, code) for fname, code in mock_repo.items()]
    
    # Step 2: Execute all tasks concurrently in parallel threads
    print(f"[Orchestrator] Launching {len(tasks)} Map Workers concurrently over Groq API...\n")
    map_outputs = await asyncio.gather(*tasks)
    
    # Step 3: Run the aggregation layer (The Reduce Gather)
    final_architecture_map = await reduce_summaries(map_outputs)
    
    total_elapsed = time.time() - global_start
    print("\n==================================================")
    print(f"🎯 GLOBAL REDO-COMPILATION COMPLETE (Total Time: {total_elapsed:.2f}s)")
    print("==================================================")
    print(f"System Overview:\n{final_architecture_map.system_overview}\n")
    print("Compiled Module Index:")
    for module in final_architecture_map.module_index:
        print(f" 📂 {module.filename}")
        print(f"    ↳ Methods: {module.exported_functions}")
        print(f"    ↳ Responsibility: {module.core_purpose}")

if __name__ == "__main__":
    if not os.environ.get("GROQ_API_KEY"):
        print("[!] ERROR: Please set your GROQ_API_KEY environment variable.")
    else:
        # Bootstraps the asynchronous event loop natively
        asyncio.run(main())