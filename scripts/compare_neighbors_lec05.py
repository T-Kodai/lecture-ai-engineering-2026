"""第5回 宿題（実装）: 通常のベクトル検索と、前後ページを足した検索で、同じ質問に答えさせて比べる。

使い方（リポジトリの直下で）:
    uv run python -m scripts.compare_neighbors_lec05 --runs 2 --out lectures/05/results/impl/compare.jsonl
    uv run python -m scripts.compare_neighbors_lec05 --summary lectures/05/results/impl/compare.jsonl  # 集計だけ

app/agent.py の通常モード（search_materials を使うエージェント）をそのまま使い、
app.retrieval.RAG_NEIGHBOR_PAGES だけを 0（通常）と 1（前後 1 ページを足す）で切り替える。
モデルに渡したページ（ツールの戻り値）、回答で引用したページ、時間・トークン数・推定費用を 1 行ずつ記録する。
"""

import argparse
import json
import re
import time
from pathlib import Path

from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ToolCallPart, ToolReturnPart

from app import retrieval
from app.agent import agent, build_model
from app.config import MODEL

QUESTIONS = {
    # 答えが 1 ページ（第2回 p.52）でそろう
    "lora": "第2回の説明では、LoRAは何を固定し何を学習しますか？ QLoRAは何を加えますか？",
    # 根拠が第2回 p.13〜15・p.18 に分かれる
    "limits": "第2回で、確率で次の言葉を選ぶ仕組みから出てくる帰結（限界）と、その付き合い方は？",
    # 根拠が第3回 p.13・39・40 に分かれる（演習の比較用の質問）
    "memory": "コンパクションとセッションをまたぐメモリの違いは？日々のメモは全部長期メモリになる？",
    # 資料に答えがない（演習の比較用の質問）
    "none": "今回作ったRAGの実測平均応答時間と正答率は？",
}
CONDITIONS = {"normal": 0, "neighbors": 1}
CITATION = re.compile(r"第\s*(\d+)\s*回[・･]?\s*PDF\s*p\.\s*(\d+(?:\s*[,、]\s*(?:p\.)?\s*\d+)*)")


def cited_pages(text: str) -> list[str]:
    pages = set()
    for lecture, numbers in CITATION.findall(text):
        for n in re.findall(r"\d+", numbers):
            pages.add(f"lec{int(lecture):02d}-p{int(n):03d}")
    return sorted(pages)


def run_once(question: str) -> dict:
    for attempt in range(5):
        try:
            started = time.perf_counter()
            result = agent.run_sync(question, model=build_model())
            seconds = time.perf_counter() - started
            break
        except ModelHTTPError as e:
            if e.status_code not in (429, 503) or attempt == 4:
                raise
            time.sleep(30)  # 混雑・レート制限のときは待ってやり直す
    queries, given = [], []
    for message in result.all_messages():
        for part in message.parts:
            if isinstance(part, ToolCallPart):
                queries.append(part.args_as_dict().get("query"))
            elif isinstance(part, ToolReturnPart) and part.tool_name == "search_materials":
                for hit in json.loads(part.content).get("results", []):
                    given.append({"page_id": hit["page_id"], "neighbor": "neighbor_of" in hit})
    usage = result.usage
    return {"output": result.output, "queries": queries, "given_pages": given,
            "cited_pages": cited_pages(result.output), "seconds": round(seconds, 2),
            "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens, "requests": usage.requests,
            "cost_usd": float(usage.cost) if usage.cost is not None else None}


def summarize(path: Path) -> None:
    """記録した JSONL を質問・条件ごとに集計する（API は呼ばない）。"""
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    print("質問     条件       回  渡したページ(うち前後)  引用した前後ページ        入力   出力   秒     USD")
    for qid in QUESTIONS:
        for condition in CONDITIONS:
            rows = sorted((r for r in records if r["question"] == qid and r["condition"] == condition),
                          key=lambda r: r["run"])
            for r in rows:
                added = {g["page_id"].replace("-main-p", "-p") for g in r["given_pages"] if g["neighbor"]}
                used = sorted(added & set(r["cited_pages"]))
                print(f"{qid:<8} {condition:<10} {r['run']}   {len(r['given_pages']):>2} ({len(added):>2})"
                      f"               {','.join(used) or '-':<24} {r['input_tokens']:>6} {r['output_tokens']:>5}"
                      f" {r['seconds']:>5} {r['cost_usd']:.6f}")
    print("\n条件ごとの平均（全質問・全回）")
    for condition in CONDITIONS:
        rows = [r for r in records if r["condition"] == condition]
        mean = lambda key: sum(r[key] for r in rows) / len(rows)
        print(f"{condition:<10} n={len(rows)} 入力 {mean('input_tokens'):,.0f} / 出力 {mean('output_tokens'):,.0f}"
              f" / {mean('seconds'):.2f} 秒 / ${mean('cost_usd'):.6f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--summary", type=Path, help="記録した JSONL を集計して表示する（API は呼ばない）")
    args = parser.parse_args()
    if args.summary:
        summarize(args.summary)
        return
    if args.out is None:
        parser.error("--out か --summary を指定してください")
    if args.out.exists():
        raise SystemExit(f"{args.out} がもうあります。別のファイルを --out に指定してください")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for run in range(1, args.runs + 1):
            for qid, question in QUESTIONS.items():
                # 回ごとに条件の順番を入れ替え、時間帯の偏りを減らす
                order = list(CONDITIONS) if run % 2 else list(reversed(CONDITIONS))
                for condition in order:
                    retrieval.RAG_NEIGHBOR_PAGES = CONDITIONS[condition]
                    record = {"model": MODEL, "question": qid, "condition": condition, "run": run} | run_once(question)
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    f.flush()
                    print(f"{qid:<7} {condition:<9} run{run}: pages={len(record['given_pages'])} "
                          f"cited={record['cited_pages']} in={record['input_tokens']} {record['seconds']}s", flush=True)
                    time.sleep(8)


if __name__ == "__main__":
    main()
