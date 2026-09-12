"""Central configuration: endpoints, model routing map, folders."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = BASE_DIR / "outputs"
SANDBOX_DIR = BASE_DIR / "sandbox"
OUTPUTS_DIR.mkdir(exist_ok=True)
SANDBOX_DIR.mkdir(exist_ok=True)

LITELLM_BASE_URL = "http://localhost:4000"
LITELLM_API_KEY = "sk-anything"  # local proxy only; no real key ever leaves the machine

# Logical model names as exposed by litellm_config.yaml
MODEL_ROUTER = "router"          # qwen2.5:7b              -> task classification
MODEL_REASONING = "reasoning"    # qwen2.5:7b              -> reports, documents, Q&A
MODEL_CODER = "coder"            # qwen2.5-coder:7b
MODEL_VISION = "vision"          # granite3.2-vision
MODEL_VISION_PRO = "vision-pro"  # minicpm-v (heavier visual reasoning)

# logical name -> actual ollama model (needed for `ollama stop` VRAM release)
OLLAMA_NAMES = {
    MODEL_ROUTER: "qwen2.5:7b",
    MODEL_REASONING: "qwen2.5:7b",   # same weights as router - no VRAM swap needed
    MODEL_CODER: "qwen2.5-coder:7b",
    "coder": "qwen2.5-coder:7b",
    MODEL_VISION: "granite3.2-vision:latest",
    MODEL_VISION_PRO: "minicpm-v:latest",
}

MAX_AGENT_STEPS = 10   # safety cap on the think->act->observe loop
CODE_TIMEOUT = 60      # seconds for sandboxed executions
AGENT_TIMEOUT = 180    # seconds for one planner response (raised for large outputs)
AGENT_MAX_TOKENS = 4096  # raised: fits full docx/pdf body, long code files in one shot
VISION_TIMEOUT = 180   # seconds for one local image-analysis request
VISION_MAX_TOKENS = 2048  # raised: richer image descriptions and OCR results
