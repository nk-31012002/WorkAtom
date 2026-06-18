# orchestrator_graph.py
import os
from typing import List, Dict, Any, TypedDict, Annotated
import operator
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langchain_groq import ChatGroq
import json
from langgraph.graph import StateGraph, END
from langchain_core.prompts import ChatPromptTemplate

# 1. Define the Global Agent Memory State
class AgentState(TypedDict):
    """The shared, stateful memory passed between our specialized agents."""
    filename: str                                # Target file being evaluated
    raw_code: str                                # The raw string of source code
    function_name: str                           # Name of the active function being parsed
    current_decomposition: Dict[str, Any]        # The latest parsed Atomic Work Units JSON
    critic_feedback: str                         # Notes from the Validator agent if a check fails
    validation_passed: bool                      # Flag to determine if we exit the loop or retry
    iterations: int                              # Counter to prevent infinite loops

# 2. Advanced Structural Schemas for Agent Outputs
class ImpactLink(BaseModel):
    step_number: int
    title: str
    category: str
    explanation: str
    affects_steps: List[int] = Field(
        description="List of step numbers downstream that are directly impacted by this step's variable changes."
    )

class VerifiedDecomposition(BaseModel):
    function_name: str
    is_valid_atomicity: bool = Field(description="True if NO single step covers more than 3 days of effort or combines distinct side effects.")
    reasons_for_rejection: str = Field(description="If invalid, detailed breakdown of exactly which step failed and why.")
    refined_steps: List[ImpactLink] = Field(description="The finalized or re-decomposed sequence of work units.")

# 3. Initialize the Core Engine Client
if not os.environ.get("GROQ_API_KEY"):
    print("[!] Warning: GROQ_API_KEY environment variable not detected.")

# Using the high-throughput 70B model for deep architectural reasoning
llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0.1,  # Low temperature for highly analytical tracking
    max_tokens=4096,
    groq_api_key=os.environ.get("GROQ_API_KEY")
)

print("\n--- Phase 2 Agentic State Machinery Initialized ---")

# ==========================================
# 4. AGENT NODES (The Processing Engines)
# ==========================================

def decomposer_agent_node(state: AgentState) -> Dict[str, Any]:
    """Agent 1: Ingests the raw code and builds the initial structural step mapping."""
    print(f"\n[Agent -> Decomposer] Slicing function '{state['function_name']}'...")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are an expert Systems Architect. Break down the provided raw Python function into "
            "clear, sequential steps matching the Pydantic structural schema.\n\n"
            "CRITICAL RULES:\n"
            "1. Strip out code variable jargon; use business operational English.\n"
            "2. Map data flow impacts via 'affects_steps' to show downstream dependencies.\n"
            "3. If the Critic Agent gave you feedback, you MUST use it to rewrite and improve the steps."
        )),
        ("user", (
            "Target Function: {function_name}\n"
            "Critic Feedback: {feedback}\n\n"
            "Raw Source Code:\n```python\n{code}\n```"
        ))
    ])
    
    # Force the LLM to output our structured type schema
    structured_llm = llm.with_structured_output(VerifiedDecomposition)
    chain = prompt | structured_llm
    
    response = chain.invoke({
        "function_name": state["function_name"],
        "feedback": state.get("critic_feedback", "None. This is your first attempt."),
        "code": state["raw_code"]
    })
    
    # Convert Pydantic object to a standard dict to store in state
    steps_dict = [step.model_dump() for step in response.refined_steps]
    
    return {
        "current_decomposition": {"steps": steps_dict},
        "iterations": state.get("iterations", 0) + 1
    }


def critic_agent_node(state: AgentState) -> Dict[str, Any]:
    """Agent 2: Acts as a strict gatekeeper validating atomicity rules and step sizes."""
    print("[Agent -> Critic Validator] Inspecting structural work boundaries...")
    
    current_steps = state["current_decomposition"].get("steps", [])
    steps_str = json.dumps(current_steps, indent=2)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a strict QA Engineering Lead. Your task is to evaluate the generated work breakdown.\n\n"
            "REJECTION CRITERIA:\n"
            "1. Reject if ANY single step takes more than 3 days of effort (e.g., combines calculations with logging).\n"
            "2. Reject if 'affects_steps' references non-existent step indices or defaults to generic sequences.\n"
            "3. Reject if code variables are leaking into descriptions.\n\n"
            "You must decide if this passes validation. If it fails, specify exactly why."
        )),
        ("user", "Evaluate these steps:\n{steps}")
    ])
    
    # We reuse the validation schema to format the critic's verdict
    structured_llm = llm.with_structured_output(VerifiedDecomposition)
    chain = prompt | structured_llm
    
    verdict = chain.invoke({"steps": steps_str})
    
    if verdict.is_valid_atomicity or state["iterations"] >= 3:
        print("  >>> [Verdict] APPROVED. Moving to completion.")
        return {"validation_passed": True, "critic_feedback": ""}
    else:
        print(f"  >>> [Verdict] REJECTED: {verdict.reasons_for_rejection}")
        return {
            "validation_passed": False, 
            "critic_feedback": verdict.reasons_for_rejection
        }

# ==========================================
# 5. CONDITIONAL EDGES & GRAPH COMPILATION
# ==========================================

def route_next_node(state: AgentState) -> str:
    """Evaluates state metrics to either loop back or close the network thread."""
    if state["validation_passed"]:
        return "complete"
    else:
        return "retry"

# Initialize state machine graph topology
workflow = StateGraph(AgentState)

# Register our agents as nodes
workflow.add_node("decomposer", decomposer_agent_node)
workflow.add_node("critic", critic_agent_node)

# Establish graph entry point
workflow.set_entry_point("decomposer")

# Draw a static edge from decomposer to critic
workflow.add_edge("decomposer", "critic")

# Add conditional routing edge away from critic
workflow.add_conditional_edges(
    "critic",
    route_next_node,
    {
        "retry": "decomposer",   # The self-correction loop back to the worker
        "complete": END          # Break out of graph
    }
)

# Compile graph memory matrix
app = workflow.compile()

# ==========================================
# 6. RUN THE AGENTIC ENGINE
# ==========================================
if __name__ == "__main__":
    import ast
    
    # Ingest our lab rat code target
    with open("target_code.py", "r") as f:
        target_source = f.read()
        
    print("\n⚡ Starting Multi-Agent Orchestration Run [Phase 2]...")
    
    initial_state = {
        "filename": "target_code.py",
        "raw_code": target_source,
        "function_name": "process_user_shopping_cart_and_handle_everything_system",
        "current_decomposition": {},
        "critic_feedback": "",
        "validation_passed": False,
        "iterations": 0
    }
    
    # Run the graph synchronously
    final_output = app.invoke(initial_state)
    
    print("\n==================================================")
    print("🎯 AGENTIC OPTIMIZATION COMPLETED")
    print(f"Total Iterations Formed: {final_output['iterations']}")
    print("==================================================")
    
    # Print the finalized, recursively verified steps
    for step in final_output["current_decomposition"]["steps"]:
        print(f"\nStep {step['step_number']}: {step['title']}")
        print(f"  Category: {step['category']}")
        print(f"  Impacts Steps: {step['affects_steps']}")
        print(f"  Explanation: {step['explanation']}")