import ast
import os
from typing import List
from pydantic import BaseModel, Field
import instructor
from openai import OpenAI

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

client = instructor.from_openai(
    OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ.get("GROQ_API_KEY")
    ),
    mode=instructor.Mode.JSON
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
        model="openai/gpt-oss-120b",
        response_model=CodeDecomposition,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=8192
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

    
    for step in result.atomic_steps:
        style_class = "state"
        if "Validation" in step.category:
            style_class = "val"
        elif "Side Effect" in step.category:
            style_class = "side"
            
        print(f'  Step{step.step_number}["Step {step.step_number}: {step.title}"]')
        print(f'  class Step{step.step_number} {style_class};')


    for step in result.atomic_steps:
        for affected in step.affects_steps:
            print(f"  Step{step.step_number} --> Step{affected}")
            
    print("```\n")
    


def extract_function_source(raw_code: str, function_name: str) -> str:
    """Extract only the requested function using Python AST."""

    tree = ast.parse(raw_code)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == function_name:
                source = ast.get_source_segment(raw_code, node)

                if source:
                    return source

    raise ValueError(
        f"Function '{function_name}' not found in source code."
    )

def analyze_and_decompose_file(raw_code: str, function_to_parse: str):

    try:
        tree = ast.parse(raw_code)

    except SyntaxError as e:
        print(f"[!] Syntax Error: {e}")
        return

    print("  -> AST Structure Generated Successfully.")

    function_source = extract_function_source(
        raw_code,
        function_to_parse
    )

    print(
        f"  -> Extracted function: {function_to_parse}"
    )

    print("  -> Contacting Breakdown Engine...")

    decomposition_result = get_atomic_breakdown(
        function_to_parse,
        function_source
    )

    print("\n==================================================")
    print("🎨 GENERATING INTERACTIVE VISUALIZATION CONTRACT")
    print("==================================================")

    generate_mermaid_chart(decomposition_result)


if __name__ == "__main__":
    from repo_crawler import RepositoryCrawler
    
    crawler = RepositoryCrawler(".")
    live_codebase = crawler.scan_repository()
    
    target_file = "target_code.py" 
    target_function = "process_order"
    
    if target_file in live_codebase:
        print(f"\n⚡ Running Structural Breakdown Pipeline on: {target_file} -> {target_function}()...")
        
        raw_code_content = live_codebase[target_file]
        
        analyze_and_decompose_file(raw_code_content, target_function)
    else:
        print(f"[!] Target file '{target_file}' not found by repository crawler.")