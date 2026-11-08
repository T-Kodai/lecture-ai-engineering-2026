"""第3回 宿題（発展 a）: 同じ質問を Pydantic AI 版と ADK 版のエージェントに投げ、ツール呼び出しと回答を記録する。

使い方（リポジトリの直下で）:
    PYTHONPATH=. uv run --with google-adk python -m scripts.compare_lec03 --runs 3 --out lectures/03/results/compare.jsonl

- Pydantic AI 版：app/agent.py の agent を、そのままプロセス内で実行する
- ADK 版：課題どおり `adk run --replay` で adk_agent/glossary_agent を実行し、保存したセッション（JSON）から
  ツール呼び出しと、LLM の応答の回数・トークン数を読む
1 回ごとに新しい会話で質問する（前の質問の履歴は持ち越さない）。
"""

import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path

from pydantic_ai.messages import ToolCallPart

from adk_agent.glossary_agent.agent import root_agent
from app.agent import agent, build_model
from app.config import MODEL

QUESTIONS = {
    "levels": "AIE2026の講座の宿題にある「3レベル」とは何ですか？",
    "lora": "LoRAとQLoRAの違いは？",
    "quiz": "第2回の内容から確認問題を1問出して",
}
ADK_AGENT_DIR = Path("adk_agent/glossary_agent")
INTERVAL = 8  # 無料枠の毎分のリクエスト数に収めるための待ち時間 [s]


def run_pydantic(question: str) -> dict:
    start = time.perf_counter()
    result = agent.run_sync(question, model=build_model())
    calls = [{"name": p.tool_name, "args": p.args_as_dict()}
             for m in result.all_messages() for p in m.parts if isinstance(p, ToolCallPart)]
    usage = result.usage
    return {"output": result.output, "tool_calls": calls, "llm_requests": usage.requests,
            "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
            "seconds": round(time.perf_counter() - start, 2)}


def run_adk(question: str, session_id: str, keep_dir: Path) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({"state": {}, "queries": [question]}, f, ensure_ascii=False)
        replay = f.name
    start = time.perf_counter()
    subprocess.run(["adk", "run", "--in_memory", "--save_session", "--session_id", session_id,
                    "--replay", replay, str(ADK_AGENT_DIR)], check=True, capture_output=True, text=True)
    seconds = round(time.perf_counter() - start, 2)  # adk の起動時間を含む
    saved = ADK_AGENT_DIR / f"{session_id}.session.json"
    session = json.loads(saved.read_text(encoding="utf-8"))
    saved.rename(keep_dir / saved.name)  # 生データとして残す

    calls, texts, requests, in_tok, out_tok = [], [], 0, 0, 0
    for event in session["events"]:
        if event.get("author") == "user":
            continue
        usage = event.get("usageMetadata")
        if usage:  # LLM の応答 1 回ごとに付く
            requests += 1
            in_tok += usage.get("promptTokenCount") or 0
            out_tok += usage.get("candidatesTokenCount") or 0
        for part in (event.get("content") or {}).get("parts") or []:
            if part.get("functionCall"):
                calls.append({"name": part["functionCall"]["name"], "args": part["functionCall"].get("args")})
            elif part.get("text") and not part.get("thought"):
                texts.append(part["text"])
    return {"output": "".join(texts), "tool_calls": calls, "llm_requests": requests,
            "input_tokens": in_tok, "output_tokens": out_tok, "seconds": seconds}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    keep_dir = out.parent / "adk_sessions"
    # 同じモデルどうしで比べる（Pydantic AI 側は AIE_MODEL に従い、ADK 側は agent.py に固定）
    if MODEL != root_agent.model:
        raise SystemExit(f"モデルが違います: Pydantic AI={MODEL}, ADK={root_agent.model}。AIE_MODEL を外して実行してください")
    # 前回の結果を上書き・混在させない（run 番号とセッションのファイル名は毎回 run1 から始まるため）
    if out.exists() or any(keep_dir.glob("*.session.json")):
        raise SystemExit(f"{out} か {keep_dir} に前回の結果があります。別のフォルダを --out に指定してください")
    keep_dir.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for run in range(1, args.runs + 1):
            for qid, question in QUESTIONS.items():
                for framework in ["pydantic_ai", "adk"]:
                    if framework == "pydantic_ai":
                        record = run_pydantic(question)
                    else:
                        record = run_adk(question, f"{qid}-run{run}", keep_dir)
                    record = {"framework": framework, "model": MODEL, "question": qid, "run": run} | record
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    f.flush()
                    calls = ", ".join(f"{c['name']}({c['args']})" for c in record["tool_calls"])
                    print(f"{framework:<11} {qid:<6} run{run} requests={record['llm_requests']} calls=[{calls}]", flush=True)
                    time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
