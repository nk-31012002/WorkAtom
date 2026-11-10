import os
from typing import List, Dict, Any, TypedDict, Annotated
import operator
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langchain_groq import ChatGroq
import json
from langgraph.graph import StateGraph, END
from langchain_core.prompts import ChatPromptTemplate

class AgentState(TypedDict):
    """The shared, stateful memory passed between our specialized agents."""
    filename: str                                # Target file being evaluated
    raw_code: str                                # The raw string of source code
    function_name: str                           # Name of the active function being parsed
    current_decomposition: Dict[str, Any]        # The latest parsed Atomic Work Units JSON
    critic_feedback: str                         # Notes from the Validator agent if a check fails
    validation_passed: bool                      # Flag to determine if we exit the loop or retry
    iterations: int                              

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

class CriticVerdict(BaseModel):
    is_valid_atomicity: bool = Field(description="True if NO single step covers more than 3 days of effort or combines distinct side effects.")
    reasons_for_rejection: str = Field(description="If invalid, detailed breakdown of exactly which step failed and why. Empty string if valid.")

if not os.environ.get("GROQ_API_KEY"):
    print("[!] Warning: GROQ_API_KEY environment variable not detected.")

llm = ChatGroq(
    model="openai/gpt-oss-120b",
    temperature=0.1,  
    max_tokens=4096,
    groq_api_key=os.environ.get("GROQ_API_KEY")
)

print("\n--- Phase 2 Agentic State Machinery Initialized ---")


def decomposer_agent_node(state: AgentState) -> Dict[str, Any]:
    """Agent 1: Ingests the raw code and builds the initial structural step mapping."""
    print(f"\n[Agent -> Decomposer] Slicing function '{state['function_name']}'...")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are an expert Systems Architect. Break down the provided raw Python function into "
            "clear, sequential steps.\n\n"
            "CRITICAL RULES:\n"
            "1. Strip out code variable jargon; use business operational English.\n"
            "2. Map data flow impacts via 'affects_steps' to show downstream dependencies.\n"
            "3. If the Critic Agent gave you feedback, you MUST use it to rewrite and improve the steps.\n"
            "4. Respond ONLY with valid JSON matching this exact structure:\n"
            "{{\"function_name\": \"...\", \"is_valid_atomicity\": true, \"reasons_for_rejection\": \"\", "
            "\"refined_steps\": [{{\"step_number\": 1, \"title\": \"...\", \"category\": \"...\", \"explanation\": \"...\", \"affects_steps\": [2]}}]}}"
        )),
        ("user", (
            "Target Function: {function_name}\n"
            "Critic Feedback: {feedback}\n\n"
            "Raw Source Code:\n```python\n{code}\n```"
        ))
    ])
    
    structured_llm = llm.with_structured_output(VerifiedDecomposition, method="json_mode")
    chain = prompt | structured_llm
    
    response = chain.invoke({
        "function_name": state["function_name"],
        "feedback": state.get("critic_feedback", "None. This is your first attempt."),
        "code": state["raw_code"]
    })
    
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
            "Respond ONLY with valid JSON matching this exact structure:\n"
            "{{\"is_valid_atomicity\": true, \"reasons_for_rejection\": \"...\"}}"
        )),
        ("user", "Evaluate these steps:\n{steps}")
    ])
    
    structured_llm = llm.with_structured_output(CriticVerdict, method="json_mode")
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



def route_next_node(state: AgentState) -> str:
    """Evaluates state metrics to either loop back or close the network thread."""
    if state["validation_passed"]:
        return "complete"
    else:
        return "retry"

workflow = StateGraph(AgentState)

workflow.add_node("decomposer", decomposer_agent_node)
workflow.add_node("critic", critic_agent_node)

workflow.set_entry_point("decomposer")

workflow.add_edge("decomposer", "critic")

workflow.add_conditional_edges(
    "critic",
    route_next_node,
    {
        "retry": "decomposer",   
        "complete": END          
    }
)

app = workflow.compile()


if __name__ == "__main__":
    from repo_crawler import RepositoryCrawler
    
    crawler = RepositoryCrawler(".")
    live_codebase = crawler.scan_repository()
    
    target_file = "target_code.py" 
    
    if target_file in live_codebase:
        print(f"\n⚡ Starting Multi-Agent Orchestration Run [Phase 2] on: {target_file}...")
        
        initial_state = {
            "filename": target_file,
            "raw_code": live_codebase[target_file],
            "function_name": "process_order", 
            "current_decomposition": {},
            "critic_feedback": "",
            "validation_passed": False,
            "iterations": 0
        }
        
        final_output = app.invoke(initial_state)
        
        print("\n==================================================")
        print("🎯 AGENTIC OPTIMIZATION COMPLETED")
        print(f"Total Iterations Formed: {final_output['iterations']}")
        print("==================================================")
        
        for step in final_output["current_decomposition"]["steps"]:
            print(f"\nStep {step['step_number']}: {step['title']}")
            print(f"  Category: {step['category']}")
            print(f"  Impacts Steps: {step['affects_steps']}")
            print(f"  Explanation: {step['explanation']}")
    else:
        print(f"[!] Target file '{target_file}' not found by repository crawler.")
