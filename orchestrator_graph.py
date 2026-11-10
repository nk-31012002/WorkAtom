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

class CriticVerdict(BaseModel):
    is_valid_atomicity: bool = Field(description="True if NO single step covers more than 3 days of effort or combines distinct side effects.")
    reasons_for_rejection: str = Field(description="If invalid, detailed breakdown of exactly which step failed and why. Empty string if valid.")

# 3. Initialize the Core Engine Client
if not os.environ.get("GROQ_API_KEY"):
    print("[!] Warning: GROQ_API_KEY environment variable not detected.")

# Using the high-throughput 70B model for deep architectural reasoning
llm = ChatGroq(
    model="openai/gpt-oss-120b",
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
# Updated execution block inside orchestrator_graph.py
if __name__ == "__main__":
    from repo_crawler import RepositoryCrawler
    
    # 1. Dynamically scan the workspace directory
    crawler = RepositoryCrawler(".")
    live_codebase = crawler.scan_repository()
    
    # 2. Pick a target file found by the crawler to deeply analyze with our agents
    # Let's target our complex e-commerce engine file dynamically!
    target_file = "target_code.py" 
    
    if target_file in live_codebase:
        print(f"\n⚡ Starting Multi-Agent Orchestration Run [Phase 2] on: {target_file}...")
        
        initial_state = {
            "filename": target_file,
            "raw_code": live_codebase[target_file],
            "function_name": "process_order", # The complex engine function inside target_code.py
            "current_decomposition": {},
            "critic_feedback": "",
            "validation_passed": False,
            "iterations": 0
        }
        
        # Run the graph synchronously through the self-correcting agents
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


# import os
# import json
# from typing import List, Dict, Any, TypedDict

# from pydantic import BaseModel, Field
# from langchain_groq import ChatGroq
# from langchain_core.prompts import ChatPromptTemplate
# from langgraph.graph import StateGraph, END


# # =========================================================
# # 1. GLOBAL CONFIGURATION
# # =========================================================

# MAX_ITERATIONS = 3

# GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# if not GROQ_API_KEY:
#     raise ValueError(
#         "GROQ_API_KEY environment variable is missing."
#     )


# # =========================================================
# # 2. GLOBAL AGENT MEMORY STATE
# # =========================================================

# class AgentState(TypedDict):
#     """Shared memory passed between specialized agents."""

#     filename: str
#     raw_code: str
#     function_name: str

#     current_decomposition: Dict[str, Any]

#     critic_feedback: str
#     validation_passed: bool
#     iterations: int


# # =========================================================
# # 3. PYDANTIC OUTPUT SCHEMAS
# # =========================================================

# class ImpactLink(BaseModel):
#     """One atomic work unit."""

#     step_number: int = Field(
#         description="Sequential step number."
#     )

#     title: str = Field(
#         description="Action-oriented title."
#     )

#     category: str = Field(
#         description="Operation category, such as Validation, State Modification, or Side Effect."
#     )

#     explanation: str = Field(
#         description="Plain-English explanation of what this step accomplishes."
#     )

#     affects_steps: List[int] = Field(
#         description="Downstream steps directly affected by changes to this step."
#     )


# class VerifiedDecomposition(BaseModel):
#     """
#     Decomposer output schema.

#     The Decomposer is responsible ONLY for creating
#     the complete atomic work breakdown.
#     """

#     function_name: str = Field(
#         description="Name of the function being decomposed."
#     )

#     refined_steps: List[ImpactLink] = Field(
#         description="Complete sequential list of atomic work units."
#     )


# class CriticVerdict(BaseModel):
#     """
#     Critic output schema.

#     The Critic is responsible ONLY for validation.
#     """

#     is_valid_atomicity: bool = Field(
#         description="True if every step is sufficiently atomic and dependencies are valid."
#     )

#     reasons_for_rejection: str = Field(
#         description="Explain all validation failures. Return an empty string if valid."
#     )


# # =========================================================
# # 4. INITIALIZE GROQ LLM
# # =========================================================

# llm = ChatGroq(
#     model="openai/gpt-oss-120b",
#     temperature=0.1,
#     max_tokens=4096,
#     groq_api_key=GROQ_API_KEY
# )

# print("\n--- Phase 2 Agentic State Machinery Initialized ---")


# # =========================================================
# # 5. AGENT 1: DECOMPOSER
# # =========================================================

# def decomposer_agent_node(state: AgentState) -> Dict[str, Any]:
#     """
#     Agent 1:
#     Converts raw source code into sequential atomic work units.
#     """

#     print(
#         f"\n[Agent -> Decomposer] "
#         f"Slicing function '{state['function_name']}'..."
#     )

#     prompt = ChatPromptTemplate.from_messages([

#         (
#             "system",
#             """
# You are an expert Systems Architect.

# Your task is to decompose a Python function into
# small, independent, sequential Atomic Work Units.

# STRICT RULES:

# 1. Use plain business-oriented English.
# 2. Avoid raw variable names and unnecessary programming jargon.
# 3. Each step must represent one distinct operation.
# 4. Separate validation, state modification, calculations,
#    external calls, and side effects.
# 5. Number steps sequentially, beginning at 1.
# 6. Identify downstream dependencies using affects_steps.
# 7. Never reference a step that does not exist.
# 8. Do not combine unrelated operations into one step.
# 9. Each step should be independently understandable.
# 10. If critic feedback is provided, correct the identified
#     problems while preserving valid existing work.

# IMPORTANT:

# You are ONLY the Decomposer.

# Do not generate a validation verdict.
# Do not generate is_valid_atomicity.
# Do not generate reasons_for_rejection.

# Return ONLY valid JSON matching this structure:

# {{
#     "function_name": "process_order",
#     "refined_steps": [
#         {{
#             "step_number": 1,
#             "title": "Validate customer order",
#             "category": "Validation Check",
#             "explanation": "Checks whether the submitted order contains valid information.",
#             "affects_steps": [2, 3]
#         }}
#     ]
# }}
# """
#         ),

#         (
#             "user",
#             """
# Target Function: {function_name}

# Previous Critic Feedback:
# {feedback}

# Raw Source Code:

# ```python
# {code}
# ```
# """
#         )

#     ])

#     structured_llm = llm.with_structured_output(
#         VerifiedDecomposition,
#         method="json_mode"
#     )

#     chain = prompt | structured_llm

#     response = chain.invoke({

#         "function_name": state["function_name"],

#         "feedback": state.get(
#             "critic_feedback",
#             "None. This is the first decomposition attempt."
#         ),

#         "code": state["raw_code"]

#     })

#     # Convert the Pydantic response into LangGraph state data.
#     steps_dict = [
#         step.model_dump()
#         for step in response.refined_steps
#     ]

#     print(
#         f"  >>> Generated {len(steps_dict)} atomic work units."
#     )

#     return {

#         "current_decomposition": {
#             "function_name": response.function_name,
#             "steps": steps_dict
#         },

#         "iterations": state.get("iterations", 0) + 1

#     }


# # =========================================================
# # 6. AGENT 2: CRITIC VALIDATOR
# # =========================================================

# def critic_agent_node(state: AgentState) -> Dict[str, Any]:
#     """
#     Agent 2:
#     Evaluates atomicity and dependency integrity.

#     IMPORTANT:
#     Uses CriticVerdict, NOT VerifiedDecomposition.
#     """

#     print(
#         "\n[Agent -> Critic Validator] "
#         "Inspecting structural work boundaries..."
#     )

#     current_steps = state["current_decomposition"].get(
#         "steps",
#         []
#     )

#     steps_str = json.dumps(
#         current_steps,
#         indent=2
#     )

#     prompt = ChatPromptTemplate.from_messages([

#         (
#             "system",
#             """
# You are a strict QA Engineering Lead.

# Your responsibility is to inspect an atomic work breakdown.

# REJECTION CRITERIA:

# 1. Reject steps combining multiple unrelated operations.
# 2. Reject steps combining distinct side effects.
# 3. Reject steps that represent excessively large units of work.
# 4. Reject references to nonexistent step numbers.
# 5. Reject invalid or inconsistent dependency relationships.
# 6. Reject descriptions containing unnecessary raw code variables.
# 7. Reject steps that are not independently understandable.

# APPROVAL CRITERIA:

# 1. Each step represents one distinct operation.
# 2. The sequence is logically understandable.
# 3. Dependencies are meaningful and valid.
# 4. Explanations use clear operational language.

# IMPORTANT:

# You are ONLY the Critic Validator.

# You MUST return exactly these two fields:

# - is_valid_atomicity
# - reasons_for_rejection

# Do NOT return function_name.
# Do NOT return refined_steps.
# Do NOT rewrite the decomposition.

# If valid, return an empty reasons_for_rejection string.

# Return ONLY valid JSON matching this structure:

# {{
#     "is_valid_atomicity": true,
#     "reasons_for_rejection": ""
# }}
# """
#         ),

#         (
#             "user",
#             """
# Function Name: {function_name}

# Evaluate these atomic work units:

# {steps}
# """
#         )

#     ])

#     # CORRECT SCHEMA: CriticVerdict
#     structured_llm = llm.with_structured_output(
#         CriticVerdict,
#         method="json_mode"
#     )

#     chain = prompt | structured_llm

#     verdict = chain.invoke({

#         "function_name": state["function_name"],

#         "steps": steps_str

#     })

#     # -----------------------------------------------------
#     # APPROVED
#     # -----------------------------------------------------

#     if verdict.is_valid_atomicity:

#         print(
#             "  >>> [Verdict] APPROVED. "
#             "Moving to completion."
#         )

#         return {

#             "validation_passed": True,

#             "critic_feedback": ""

#         }

#     # -----------------------------------------------------
#     # REJECTED
#     # -----------------------------------------------------

#     print(
#         f"  >>> [Verdict] REJECTED: "
#         f"{verdict.reasons_for_rejection}"
#     )

#     return {

#         "validation_passed": False,

#         "critic_feedback": verdict.reasons_for_rejection

#     }


# # =========================================================
# # 7. CONDITIONAL ROUTING
# # =========================================================

# def route_next_node(state: AgentState) -> str:
#     """
#     Routes execution based on Critic feedback.

#     APPROVED:
#         End the graph.

#     REJECTED:
#         Retry through Decomposer.

#     MAX ITERATIONS:
#         Stop without falsely marking the result approved.
#     """

#     if state["validation_passed"]:
#         return "complete"

#     if state["iterations"] >= MAX_ITERATIONS:

#         print(
#             "\n[!] Maximum retry limit reached. "
#             "Stopping with an unapproved decomposition."
#         )

#         return "failed"

#     return "retry"


# # =========================================================
# # 8. BUILD LANGGRAPH WORKFLOW
# # =========================================================

# workflow = StateGraph(AgentState)


# # Register agents.
# workflow.add_node(
#     "decomposer",
#     decomposer_agent_node
# )

# workflow.add_node(
#     "critic",
#     critic_agent_node
# )


# # Entry point.
# workflow.set_entry_point("decomposer")


# # Decomposer -> Critic.
# workflow.add_edge(
#     "decomposer",
#     "critic"
# )


# # Critic -> Retry or Completion.
# workflow.add_conditional_edges(

#     "critic",

#     route_next_node,

#     {
#         "retry": "decomposer",

#         "complete": END,

#         "failed": END
#     }

# )


# # Compile workflow.
# app = workflow.compile()


# # =========================================================
# # 9. EXECUTION ENGINE
# # =========================================================

# if __name__ == "__main__":

#     from repo_crawler import RepositoryCrawler

#     # -----------------------------------------------------
#     # STEP 1: SCAN REPOSITORY
#     # -----------------------------------------------------

#     crawler = RepositoryCrawler(".")

#     live_codebase = crawler.scan_repository()

#     target_file = "target_code.py"

#     target_function = "process_order"

#     # -----------------------------------------------------
#     # STEP 2: CHECK TARGET FILE
#     # -----------------------------------------------------

#     if target_file not in live_codebase:

#         print(
#             f"\n[!] Target file '{target_file}' "
#             "not found by repository crawler."
#         )

#         raise SystemExit(1)

#     print(
#         f"\n⚡ Starting Multi-Agent Orchestration Run "
#         f"[Phase 2] on: {target_file}..."
#     )

#     # -----------------------------------------------------
#     # STEP 3: INITIALIZE SHARED AGENT STATE
#     # -----------------------------------------------------

#     initial_state: AgentState = {

#         "filename": target_file,

#         "raw_code": live_codebase[target_file],

#         "function_name": target_function,

#         "current_decomposition": {},

#         "critic_feedback": "",

#         "validation_passed": False,

#         "iterations": 0

#     }

#     # -----------------------------------------------------
#     # STEP 4: RUN AGENTIC GRAPH
#     # -----------------------------------------------------

#     try:

#         final_output = app.invoke(initial_state)

#     except Exception as e:

#         print(
#             f"\n[!] Orchestration failed: {e}"
#         )

#         raise

#     # -----------------------------------------------------
#     # STEP 5: DISPLAY RESULTS
#     # -----------------------------------------------------

#     print("\n" + "=" * 55)

#     if final_output["validation_passed"]:

#         print("🎯 AGENTIC OPTIMIZATION COMPLETED")

#     else:

#         print("⚠️ AGENTIC OPTIMIZATION NEEDS REVIEW")

#     print("=" * 55)

#     print(
#         f"Function: {target_function}"
#     )

#     print(
#         f"Total Iterations: {final_output['iterations']}"
#     )

#     print(
#         f"Validation Passed: "
#         f"{final_output['validation_passed']}"
#     )

#     print("=" * 55)

#     # -----------------------------------------------------
#     # STEP 6: PRINT ATOMIC WORK UNITS
#     # -----------------------------------------------------

#     steps = final_output[
#         "current_decomposition"
#     ].get("steps", [])

#     for step in steps:

#         print(
#             f"\nStep {step['step_number']}: "
#             f"{step['title']}"
#         )

#         print(
#             f"  Category: {step['category']}"
#         )

#         print(
#             f"  Impacts Steps: {step['affects_steps']}"
#         )

#         print(
#             f"  Explanation: {step['explanation']}"
#         )

#     # -----------------------------------------------------
#     # STEP 7: PRINT CRITIC FEEDBACK IF UNAPPROVED
#     # -----------------------------------------------------

#     if not final_output["validation_passed"]:

#         print("\n[!] Final Critic Feedback:")

#         print(
#             final_output["critic_feedback"]
#         )

#     print("\n--- Phase 2 Execution Finished ---")
