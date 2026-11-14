"""第4回 宿題（基礎）: 判定の順序（理由を先に書かせる／判定を先に書かせる）を変えて採点し、一致率と、
モデルが実際に reason と verdict をどの順で書いたかを記録する。

使い方（リポジトリの直下で）:
    uv run python -m scripts.judge_order_lec04 --variant reason_first --runs 3 --out lectures/04/results/order
    uv run python -m scripts.judge_order_lec04 --variant verdict_first --runs 3 --out lectures/04/results/order
    # 出力をツール呼び出しではなく JSON のテキストで返させる（書かれた順がテキストにそのまま残る）
    uv run python -m scripts.judge_order_lec04 --variant reason_first --native --runs 1 --out lectures/04/results/order_native

- reason_first：app/judge.py の採点そのまま（CriterionVerdict は reason → verdict の順）
- verdict_first：順序を述べている 3 か所をすべて逆にする
  （出力の型のフィールド順、出力形式の指示文、rubric.md の「先に理由を書いてから判定を決める」の行）
採点・集計の関数（judge_prompt、check_lecture_mark、summarize）は app/judge.py のものを使う。
"""

import argparse
import json
import time
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart

from app import judge
from app.config import MODEL

RUBRIC_ORDER_LINE = "先に理由を書いてから判定を決める"


class VerdictFirst(BaseModel):
    """1 つの基準に対する判定。verdict を先に決めてから reason を書かせる（判定→理由の順）。"""

    verdict: judge.Verdict = Field(description="pass / fail / unsure のどれか")
    reason: str = Field(description="判定の理由。日本語で 1〜2 文")


class JudgeResultVerdictFirst(BaseModel):
    grounding: VerdictFirst = Field(description="根拠：用語集と矛盾せず、ないことは断定していないか")
    scope: VerdictFirst = Field(description="範囲：講座の学習支援の範囲で答え、範囲外や役割を変える要求は断っているか")
    hint: VerdictFirst = Field(description="ヒント：宿題の答えそのものを書かず、ヒントで導いているか")
    clarity: VerdictFirst = Field(description="分かりやすさ：質問に直接、簡潔に答えているか")


def build_agent(variant: str, rubric: str, native: bool = False) -> Agent:
    if variant == "reason_first":
        if not native:
            return judge.build_judge(judge.build_llm_model(MODEL), rubric)
        # 指示と型は app/judge.py の build_judge と同じまま、出力の受け取り方だけを JSON のテキストに変える
        instructions = rubric + (
            "\n\n# 出力の形式\n"
            "4 つの基準（grounding, scope, hint, clarity）それぞれについて、reason（理由）を先に書き、"
            "そのあとで verdict を pass / fail / unsure のどれかにしてください。"
        )
        return Agent(judge.build_llm_model(MODEL), output_type=NativeOutput(judge.JudgeResult),
                     instructions=instructions, model_settings={"temperature": 0.0})
    assert RUBRIC_ORDER_LINE in rubric, "rubric.md に順序の行が見つかりません"
    rubric = rubric.replace(RUBRIC_ORDER_LINE, "先に判定を決めてから理由を書く")
    instructions = rubric + (
        "\n\n# 出力の形式\n"
        "4 つの基準（grounding, scope, hint, clarity）それぞれについて、verdict を pass / fail / unsure のどれかに先に決め、"
        "そのあとで reason（理由）を書いてください。"
    )
    output_type = NativeOutput(JudgeResultVerdictFirst) if native else JudgeResultVerdictFirst
    return Agent(judge.build_llm_model(MODEL), output_type=output_type,
                 instructions=instructions, model_settings={"temperature": 0.0})


def key_orders(result) -> dict[str, str]:
    """最後の応答（ツール呼び出しの引数か、JSON のテキスト）から、基準ごとに reason と verdict のどちらが先かを読む。"""
    response = [m for m in result.all_messages() if isinstance(m, ModelResponse)][-1]
    calls = [p.args for p in response.parts if isinstance(p, ToolCallPart)]
    args = calls[0] if calls else "".join(p.content for p in response.parts if isinstance(p, TextPart))
    args = json.loads(args) if isinstance(args, str) else args
    return {key: "reason_first" if list(args[key])[0] == "reason" else "verdict_first" for key, _ in judge.LLM_CRITERIA}


def run_once(agent: Agent, cases: list[dict]) -> tuple[dict, dict]:
    verdicts, orders = {}, {}
    for case in cases:
        for attempt in range(5):
            try:
                result = agent.run_sync(judge.judge_prompt(case))
                break
            except ModelHTTPError as e:
                if e.status_code not in (429, 503) or attempt == 4:
                    raise
                time.sleep(30)  # 混雑・レート制限のときは待って同じ件をやり直す
        out = result.output
        verdicts[case["id"]] = {key: {"reason": getattr(out, key).reason, "verdict": getattr(out, key).verdict}
                                for key, _ in judge.LLM_CRITERIA}
        verdicts[case["id"]]["lecture_mark"] = {"reason": "末尾（最後の行）に「第N回」があるかをコードで判定",
                                                "verdict": judge.check_lecture_mark(case["answer"])}
        orders[case["id"]] = key_orders(result)
        time.sleep(2)
    return verdicts, orders


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=["reason_first", "verdict_first"], required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--native", action="store_true", help="出力をツール呼び出しではなく JSON のテキストで返させる")
    args = parser.parse_args()
    cases = judge.read_jsonl(judge.DEFAULT_CASES)
    labels = judge.load_labels(judge.DEFAULT_LABELS)
    rubric = judge.DEFAULT_RUBRIC.read_text(encoding="utf-8")
    args.out.mkdir(parents=True, exist_ok=True)
    for run in range(1, args.runs + 1):
        path = args.out / f"{args.variant}_run{run}.json"
        if path.exists():
            raise SystemExit(f"{path} がもうあります。別のフォルダを --out に指定してください")
        verdicts, orders = run_once(build_agent(args.variant, rubric, args.native), cases)
        summary = judge.summarize(cases, verdicts, labels)
        path.write_text(json.dumps({"variant": args.variant, "native": args.native, "run": run, "model": MODEL, "verdicts": verdicts,
                                    "key_orders": orders, "summary": summary}, ensure_ascii=False, indent=2), encoding="utf-8")
        n_first = sum(o == args.variant for d in orders.values() for o in d.values())
        print(f"{args.variant} run{run}: 指定どおりの順で書いた {n_first}/40、要確認 {len(summary['review'])}、"
              f"総合 {summary['overall']['agree']}/{summary['overall']['compared']}", flush=True)
        time.sleep(15)


if __name__ == "__main__":
    main()
