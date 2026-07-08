import os
import asyncio
import time
from typing import List, Dict, Any
from pydantic import BaseModel, Field
import instructor
from openai import AsyncOpenAI

from repo_crawler import RepositoryCrawler

class FileSummary(BaseModel):
    filename: str
    exported_functions: List[str] = Field(description="Names of top-level functions or classes found in this file.")
    core_purpose: str = Field(description="One-sentence high-level summary of what this module handles.")

class SystemArchitectureMap(BaseModel):
    total_files_processed: int
    system_overview: str = Field(description="A cohesive summary explaining how these files collaborate.")
    module_index: List[FileSummary]

async_client = instructor.from_openai(
    AsyncOpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ.get("GROQ_API_KEY")
    ),
    mode=instructor.Mode.JSON
)

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
    response = await async_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        response_model=FileSummary,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1
    )
    elapsed = time.time() - start_time
    print(f"[Map Worker] ✅ Finished: {filename} in {elapsed:.2f}s")
    return response

async def reduce_summaries(summaries: List[FileSummary]) -> SystemArchitectureMap:
    """Compiles all independent map outputs into a singular, cohesive global structural index."""
    print(f"\n[Reduce Engine] 📥 Aggregating {len(summaries)} file summaries into global index...")
    
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

async def main():

    target_repo_folder = "." 
    

    crawler = RepositoryCrawler(target_repo_folder)
    live_codebase = crawler.scan_repository()
    
    if not live_codebase:
        print("[!] No scan targets resolved. Terminating process.")
        return

    print("\n⚡ Initializing Asynchronous Map-Reduce Pipeline...")
    global_start = time.time()
    
    tasks = [map_parse_file(fname, code) for fname, code in live_codebase.items()]
    
    print(f"[Orchestrator] Launching {len(tasks)} Map Workers concurrently over Groq API...\n")
    map_outputs = await asyncio.gather(*tasks)
    
    final_architecture_map = await reduce_summaries(map_outputs)
    
    total_elapsed = time.time() - global_start
    print("\n==================================================")
    print(f"🎯 REPOSITORY COMPILATION COMPLETE (Total Time: {total_elapsed:.2f}s)")
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
        asyncio.run(main())
