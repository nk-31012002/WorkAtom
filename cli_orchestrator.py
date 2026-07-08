# cli_orchestrator.py
import os
import asyncio
import argparse
from repo_crawler import RepositoryCrawler
from async_map_reduce import map_parse_file, reduce_summaries
from parser_mvp import get_atomic_breakdown, generate_mermaid_chart

def parse_arguments():
    parser = argparse.ArgumentParser(
        description="🚀 Atomic Orchestrator: Autonomous Multi-Language Repository Decomposition Engine"
    )
    parser.add_index = parser.add_argument(
        "path", 
        type=str, 
        nargs="?", 
        default=".", 
        help="Path to the root directory of the codebase you want to analyze (Defaults to current directory)"
    )
    return parser.parse_args()

async def run_pipeline():
    args = parse_arguments()
    target_path = os.path.abspath(args.path)
    
    print("\n==================================================================")
    print("🤖 Welcome to the Atomic Orchestrator Terminal Interface")
    print("==================================================================")
    
    # Phase 1: Initialize System Crawl
    crawler = RepositoryCrawler(target_path)
    live_codebase = crawler.scan_repository()
    
    if not live_codebase:
        print("[!] No compatible files discovered. Exiting.")
        return

    # Phase 2: Asynchronous High-Speed System Mapping
    print("\n⚡ Running Asynchronous Global Repository Map-Reduce Indexing...")
    tasks = [map_parse_file(fname, code) for fname, code in live_codebase.items()]
    map_outputs = await asyncio.gather(*tasks)
    
    global_architecture = await reduce_summaries(map_outputs)
    
    print("\n==================================================================")
    print("🌐 GLOBAL SYSTEM ARCHITECTURE SUMMARY")
    print("==================================================================")
    print(global_architecture.system_overview)
    print("\n📂 DISCOVERED FILE DIRECTORY:")
    
    for i, module in enumerate(global_architecture.module_index, 1):
        print(f" [{i}] {module.filename}")
        print(f"     ↳ Core Responsibility: {module.core_purpose}")
    
    # Phase 3: Interactive Deep Dive Selection
    print("\n==================================================================")
    print("🔍 DEEP INTEGRITY COMPILATION & VISUALIZATION")
    print("==================================================================")
    
    try:
        selection = int(input("\nEnter the number [#] of the specific file you want to visually flowchart: ")) - 1
        if 0 <= selection < len(global_architecture.module_index):
            chosen_file = global_architecture.module_index[selection].filename
            raw_code = live_codebase[chosen_file]
            
            print(f"\nTargeting functions in: {chosen_file}")
            print(f"Available entry points: {global_architecture.module_index[selection].exported_functions}")
            target_func = input("Type the name of the function you want to decompose completely: ").strip()
            
            print(f"\n🎨 Executing Structural Breakdown Pipeline on {chosen_file} -> {target_func}()...")
            
            decomposition_result = get_atomic_breakdown(target_func, raw_code)
            generate_mermaid_chart(decomposition_result)
            
            print("💡 Copy the Mermaid block above and paste it into http://mermaid.live to see your colored flowchart!")
        else:
            print("[!] Invalid index selection. Exiting CLI execution loop.")
    except ValueError:
        print("[!] Input error. Please pass an integer index.")

if __name__ == "__main__":
    if not os.environ.get("GROQ_API_KEY"):
        print("[!] ERROR: Please set your GROQ_API_KEY environment variable.")
    else:
        asyncio.run(run_pipeline())
