"""第1回 宿題（発展）: 応答時間とトークン数を、複数のモデル・質問で計測する。

使い方:
    # 計測（モデル × 質問 × 回数）。結果は 1 リクエスト 1 行の JSONL に追記する
    uv run python -m scripts.bench_lec01 run --models gemini-3.5-flash-lite,gemini-3.8-flash \\
        --runs 3 --interval 13 --out lectures/01/results/bench.jsonl

    # レート制限の観察：短い質問を間隔なしで連続して送り、429 が返り始める回数を見る
    uv run python -m scripts.bench_lec01 burst --model gemini-3.5-flash-lite --count 20 \\
        --out lectures/01/results/burst.jsonl

    # 集計（Markdown の表を出力する）
    uv run python -m scripts.bench_lec01 summary lectures/01/results/bench.jsonl

エラー（429 / 503 など）は再試行せず、そのまま 1 行として記録する。
レート制限にどう当たるかも計測結果の一部として扱うため。
"""

import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from google import genai
from google.genai import errors

from app.config import get_api_key

# 性質の違う 3 問：一般的な用語（長めの説明）、講座に固有のこと、出力の長さを指定したもの
QUESTIONS = {
    "general": "LoRAとは何ですか？",
    "course": "AIE2026の講座の宿題にある「3レベル」とは何ですか？",
    "short": "LoRAとは何ですか？1文で答えてください。",
}
BURST_QUESTION = "1+1は？数字だけで答えてください。"


def measure(client: genai.Client, model: str, question: str) -> dict:
    """1 回呼び出し、応答時間・トークン数・エラーを dict にして返す。"""
    record = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": model,
    }
    start = time.perf_counter()
    try:
        response = client.models.generate_content(model=model, contents=question)
    except errors.APIError as e:
        record |= {
            "status": e.code,
            "latency_s": round(time.perf_counter() - start, 3),
            "error": (e.message or "")[:200],
        }
        return record
    latency = time.perf_counter() - start

    usage = response.usage_metadata
    record |= {
        "status": 200,
        # 実際に応答したモデル。転送（例: 非推奨モデル → 後継）されると指定と変わる
        "model_version": response.model_version,
        "latency_s": round(latency, 3),
        "input_tokens": usage.prompt_token_count,
        "output_tokens": usage.candidates_token_count,
        "thought_tokens": usage.thoughts_token_count or 0,
        "total_tokens": usage.total_token_count,
        "chars": len(response.text or ""),
        "text": response.text,
    }
    return record


def append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def show(record: dict) -> None:
    if record["status"] == 200:
        print(
            f"{record['model']:<24} {record.get('question', '-'):<8} "
            f"{record['latency_s']:6.2f}s  in {record['input_tokens']:>4}  "
            f"out {record['output_tokens']:>5}  think {record['thought_tokens']:>5}"
        )
    else:
        print(f"{record['model']:<24} {record.get('question', '-'):<8} ERROR {record['status']}")


def cmd_run(args: argparse.Namespace) -> None:
    client = genai.Client(api_key=get_api_key())
    out = Path(args.out)
    questions = args.questions.split(",") if args.questions else list(QUESTIONS)
    for model in args.models.split(","):
        # 同じ質問を連続させず、質問を 1 周ずつ回す（時間帯による揺れを質問間で平均化する）
        for run in range(1, args.runs + 1):
            for qid in questions:
                record = measure(client, model, QUESTIONS[qid]) | {"question": qid, "run": run}
                append(out, record)
                show(record)
                time.sleep(args.interval)


def cmd_burst(args: argparse.Namespace) -> None:
    client = genai.Client(api_key=get_api_key())
    out = Path(args.out)
    t0 = time.perf_counter()
    for i in range(1, args.count + 1):
        record = measure(client, args.model, BURST_QUESTION)
        record |= {"question": "burst", "seq": i, "elapsed_s": round(time.perf_counter() - t0, 2)}
        append(out, record)
        print(f"#{i:>2} t={record['elapsed_s']:6.2f}s status={record['status']}")


def cmd_summary(args: argparse.Namespace) -> None:
    records = [json.loads(line) for line in Path(args.path).read_text(encoding="utf-8").splitlines()]
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in records:
        groups.setdefault((r["model"], r["question"]), []).append(r)

    print("| モデル | 質問 | 成功/試行 | 応答時間 中央値 [s] (最小〜最大) | 入力 | 出力 中央値 | 思考 中央値 | (出力+思考) tok/s |")
    print("|---|---|---|---|---|---|---|---|")
    for (model, qid), rs in groups.items():
        ok = [r for r in rs if r["status"] == 200]
        errs = [str(r["status"]) for r in rs if r["status"] != 200]
        n = f"{len(ok)}/{len(rs)}" + (f"（{','.join(errs)}）" if errs else "")
        if not ok:
            print(f"| {model} | {qid} | {n} | - | - | - | - | - |")
            continue
        lat = [r["latency_s"] for r in ok]
        # 思考トークンも生成に時間がかかるので、速度は（出力＋思考）÷ 応答時間で見る
        speed = [(r["output_tokens"] + r["thought_tokens"]) / r["latency_s"] for r in ok]
        print(
            f"| {model} | {qid} | {n} "
            f"| {statistics.median(lat):.2f} ({min(lat):.2f}〜{max(lat):.2f}) "
            f"| {ok[0]['input_tokens']} "
            f"| {statistics.median(r['output_tokens'] for r in ok):.0f} "
            f"| {statistics.median(r['thought_tokens'] for r in ok):.0f} "
            f"| {statistics.median(speed):.0f} |"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="応答時間とトークン数を計測する")
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("run", help="モデル × 質問 × 回数で計測する")
    p.add_argument("--models", required=True, help="カンマ区切りのモデル名")
    p.add_argument("--questions", help=f"カンマ区切りの質問ID（既定: {','.join(QUESTIONS)}）")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--interval", type=float, default=5.0, help="リクエスト間の待ち時間 [s]")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("burst", help="間隔なしで連続して送り、レート制限を観察する")
    p.add_argument("--model", required=True)
    p.add_argument("--count", type=int, default=20)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_burst)

    p = sub.add_parser("summary", help="JSONL を集計して Markdown の表にする")
    p.add_argument("path")
    p.set_defaults(func=cmd_summary)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
