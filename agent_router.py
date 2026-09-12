from typing import TypedDict
import subprocess
from openai import OpenAI
from langgraph.graph import StateGraph, END

client = OpenAI(api_key="sk-anything", base_url="http://localhost:4000")

# maps logical LiteLLM name -> actual Ollama model name (needed for `ollama stop`)
OLLAMA_MODEL_NAMES = {
    "router": "qwen2.5:7b",
    "reasoning": "llama3.2",
    "vision": "granite3.2-vision:latest",
    "coder": "qwen2.5-coder:7b",
}

def unload_model(logical_name: str):
    """Force Ollama to release this model's VRAM before loading the next one."""
    ollama_name = OLLAMA_MODEL_NAMES[logical_name]
    print(f"[UNLOAD] Stopping {ollama_name}...")
    subprocess.run(["ollama", "stop", ollama_name], capture_output=True)

class AgentState(TypedDict):
    task: str
    task_type: str
    result: str

def classify_task(state: AgentState) -> AgentState:
    task = state["task"]
    classification_prompt = f"""Classify the task below into exactly one category: coding, vision, or reasoning.

Rules:
- "coding" = writing, debugging, or explaining code
- "vision" = understanding images, scanned documents, drawings, or photos
- "reasoning" = everything else: summarizing, writing reports, analysis, general Q&A

Respond with ONLY the single category word. No punctuation, no explanation.

Examples:
Task: Write a function to reverse a string
Answer: coding

Task: Summarize this maintenance log
Answer: reasoning

Task: What does this scanned drawing show?
Answer: vision

Task: {task}
Answer:"""

    response = client.chat.completions.create(
        model="router",
        messages=[{"role": "user", "content": classification_prompt}],
        temperature=0
    )
    raw_output = response.choices[0].message.content.strip().lower()
    print(f"[DEBUG] Router output: '{raw_output}'")

    if "coding" in raw_output:
        task_type = "coding"
    elif "vision" in raw_output:
        task_type = "vision"
    else:
        task_type = "reasoning"

    state["task_type"] = task_type

    # Release the router model's VRAM before the worker model loads
    unload_model("router")

    return state

def run_reasoning(state: AgentState) -> AgentState:
    response = client.chat.completions.create(
        model="reasoning",
        messages=[{"role": "user", "content": state["task"]}]
    )
    state["result"] = response.choices[0].message.content
    unload_model("reasoning")
    return state

def run_coder(state: AgentState) -> AgentState:
    response = client.chat.completions.create(
        model="coder",
        messages=[{"role": "user", "content": state["task"]}]
    )
    state["result"] = response.choices[0].message.content
    unload_model("coder")
    return state

def run_vision(state: AgentState) -> AgentState:
    response = client.chat.completions.create(
        model="vision",
        messages=[{"role": "user", "content": state["task"]}]
    )
    state["result"] = response.choices[0].message.content
    unload_model("vision")
    return state

graph = StateGraph(AgentState)
graph.add_node("classify", classify_task)
graph.add_node("reasoning", run_reasoning)
graph.add_node("coder", run_coder)
graph.add_node("vision", run_vision)

graph.set_entry_point("classify")

def route_decision(state: AgentState) -> str:
    return state["task_type"]

graph.add_conditional_edges(
    "classify",
    route_decision,
    {"reasoning": "reasoning", "coding": "coder", "vision": "vision"}
)

graph.add_edge("reasoning", END)
graph.add_edge("coder", END)
graph.add_edge("vision", END)

app = graph.compile()

if __name__ == "__main__":
    tasks = [
        "Write a Python function that checks if a pressure reading exceeds a safety threshold.",
        "Summarize the key sections that should appear in a refinery inspection report.",
    ]
    for t in tasks:
        result = app.invoke({"task": t, "task_type": "", "result": ""})
        print(f"\n--- Task: {t}\nRouted to: {result['task_type']}\nResult: {result['result']}\n")