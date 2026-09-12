"""CLI entry point:  python run_agent.py "<task>" [--image path]"""
import argparse

from workbench import config
from workbench.agent import app
from workbench.llm import unload


def main():
    ap = argparse.ArgumentParser(description="Sovereign offline agent workbench")
    ap.add_argument("task", help="natural language task for the agent")
    ap.add_argument("--image", default="", help="optional attached image / scanned document")
    args = ap.parse_args()

    task = args.task
    if args.image:
        task += (f"\n\n[Attached file: {args.image} - you can use ocr_image(path) and "
                 "analyze_image(path, question) on it.]")

    print("=" * 72, flush=True)
    print("SOVEREIGN AI WORKBENCH - offline agent run (no external calls)", flush=True)
    print("=" * 72, flush=True)

    result = app.invoke({
        "task": task, "image": args.image, "task_type": "", "worker": "",
        "transcript": [], "steps": 0, "pending": {}, "history": [],
        "files_read": [], "files_written": [], "verified": False, "post_success": 0,
        "blank_streak": 0,
        "final_answer": "", "done": False,
    })

    print("\n" + "=" * 72, flush=True)
    print("FINAL ANSWER", flush=True)
    print("=" * 72, flush=True)
    print(result.get("final_answer")
          or "(agent hit the step limit without a final answer - see trace above)")

    for m in (config.MODEL_REASONING, config.MODEL_CODER,
              config.MODEL_VISION, config.MODEL_VISION_PRO):
        unload(m)
    print("\nDeliverables: outputs/   Code sandbox: sandbox/", flush=True)


if __name__ == "__main__":
    main()
