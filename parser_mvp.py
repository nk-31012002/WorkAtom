# parser_mvp.py
import ast
import os
from typing import List
from pydantic import BaseModel, Field
import instructor
from openai import OpenAI

# 1. Define the Strict Atomic Output Schema
class AtomicWorkUnit(BaseModel):
    step_number: int = Field(description="The sequential step order number")
    title: str = Field(description="Action-oriented title starting with a clear verb")
    clear_explanation: str = Field(description="Plain-English explanation of what this block does.")
    category: str = Field(description="The type of operation, e.g., 'Validation Check', 'State Modification', 'Side Effect'")
    affects_steps: List[int] = Field(description="List of step numbers downstream that are directly affected if the logic inside this step changes.")

class CodeDecomposition(BaseModel):
    function_name: str
    high_level_purpose: str
    atomic_steps: List[AtomicWorkUnit]

# 2. Initialize the Structured LLM Client configured for GROQ
client = instructor.from_openai(
    OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ.get("GROQ_API_KEY")
    )
)

def get_atomic_breakdown(function_name: str, function_source: str) -> CodeDecomposition:
    """Passes the raw function code to Groq and demands a structured atomic breakdown."""
    
    prompt = f"""
    You are the core engine of the Atomic Orchestrator. 
    Your job is to take complex, entangled enterprise code and break it down into clean, 
    sequential "Atomic Work Units" so a brand new junior engineer or non-technical teammate 
    can understand exactly what is happening under the hood.

    Rules:
    1. Strip away all raw variable names, code syntax (like loops, arrays, dicts) in the explanations.
    2. Translate technical jargon into plain, operational business logic.
    3. Keep steps completely distinct and sequential.
    4. For each step, analyze which *future* step numbers will be impacted or affected if this step's variables or logic change, and put them in 'affects_steps'.

    Target Function Name: {function_name}
    Raw Code:
    ```python
    {function_source}
    ```
    """

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        response_model=CodeDecomposition,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    return response

def generate_mermaid_chart(result: CodeDecomposition):
    print("\n[Visualizer] Generating Mermaid.js Dependency Flowchart...\n")
    print("```mermaid")
    print("graph TD")
    print("  %% Style Definitions")
    print("  classDef val fill:#f9f,stroke:#333,stroke-width:2px;")
    print("  classDef state fill:#bbf,stroke:#333,stroke-width:2px;")
    print("  classDef side fill:#fbb,stroke:#333,stroke-width:2px;")
    
    # 1. Generate Nodes
    for step in result.atomic_steps:
        style_class = "state"
        if "Validation" in step.category:
            style_class = "val"
        elif "Side Effect" in step.category:
            style_class = "side"
            
        print(f'  Step{step.step_number}["Step {step.step_number}: {step.title}"]')
        print(f'  class Step{step.step_number} {style_class};')

    # 2. Generate Impact Arrows
    for step in result.atomic_steps:
        for affected in step.affects_steps:
            print(f"  Step{step.step_number} --> Step{affected}")
            
    print("```\n")

def analyze_and_decompose_file(filename):
    with open(filename, "r") as file:
        source_code = file.read()
        
    tree = ast.parse(source_code)
    
    print(f"=== Running Atomic Orchestrator [Phase 1] on {filename} ===")
    
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            function_source = ast.get_source_segment(source_code, node)
            
            print(f"\n[Extracting] Sending '{node.name}' to Groq Decomposition Engine...")
            
            result = get_atomic_breakdown(node.name, function_source)
            
            print("\n==================================================")
            print(f"FUNCTION: {result.function_name}")
            print(f"OVERVIEW: {result.high_level_purpose}")
            print("==================================================")
            
            for step in result.atomic_steps:
                print(f"\nStep {step.step_number}: {step.title}")
                print(f"  Category: {step.category}")
                print(f"  What happens: {step.clear_explanation}")
                print(f"  Affects Downstream Steps: {step.affects_steps}")
            print("\n==================================================")
            
            # --- CRITICAL FIX: CALL THE VISUALIZER HERE ---
            generate_mermaid_chart(result)

if __name__ == "__main__":
    if not os.environ.get("GROQ_API_KEY"):
        print("\n[!] ERROR: Please set your GROQ_API_KEY environment variable before running.")
    else:
        analyze_and_decompose_file("target_code.py")