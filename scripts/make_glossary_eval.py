"""第2回 宿題（発展）: 用語集で学習したモデルを評価する質問と正解を作る。

使い方:
    uv run python scripts/make_glossary_eval.py > lectures/02/glossary_eval.json

質問は 4 区分。正解は「answer に含まれるべき語句」のグループで持つ（グループ内はどれか 1 つ、グループはすべて必要）。
- seen: 学習データと同じ言い回し（make_sft_dataset.py の 1 つ目のテンプレート）。覚えたかを見る
- paraphrase: 学習データに無い言い回し。別名で聞く（alias）か、定義から用語名を聞く（reverse）
- unknown_course: 講座に固有らしいが用語集に無い架空の用語。「分からない」と言えるかを見る
- general: 用語集に無い一般的な用語。元の能力が壊れていないかを見る
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GLOSSARY = ROOT / "data" / "glossary.json"
SFT_TEMPLATE = "「{term}」とは何ですか？"  # make_sft_dataset.py の TEMPLATES[0] と同じ

# term_id: (seen の正解, [(paraphrase の質問, 種類, 正解)])
IN_GLOSSARY = {
    # 講座に固有の用語（基盤モデルは知らないはず）
    "homework-levels": ([["基礎"], ["実装"], ["発展"]],
                        [("AIE2026の宿題で選べる3つの段階を教えてください。", "alias", [["基礎"], ["実装"], ["発展"]])]),
    "lec-start-tag": ([["タグ"], ["開始", "始め"]],
                      [("AIE2026の講座repoにある lec03-start は何のためのものですか？", "alias", [["タグ"], ["開始", "始め"]])]),
    "default-model": ([["gemini-3.5-flash-lite"]],
                      [("AIE2026の演習と宿題で標準に使うモデルは何ですか？", "reverse", [["gemini-3.5-flash-lite"]])]),
    "answer-md": ([["結果", "解答"], ["PR", "プルリクエスト", "提出"]],
                  [("AIE2026で演習・宿題の結果を書いて提出するファイルの名前は何ですか？", "reverse", [["answer.md"]])]),
    "pi": ([["コーディングエージェント", "エージェント"], ["ターミナル", "オープンソース", "MIT"]],
           [("Pi coding agent はどんなツールですか？", "alias", [["コーディングエージェント", "エージェント"], ["ターミナル", "オープンソース", "MIT"]])]),
    "test-model": ([["Pydantic"], ["テスト"]],
                   [("Pydantic AIで、実際のLLMを呼ばずにエージェントをテストするための偽モデルは何ですか？", "reverse", [["TestModel"]])]),
    # 一般的な用語（基盤モデルもある程度知っているはず）
    "lora": ([["低ランク"], ["固定", "凍結"]],
             [("Low-Rank Adaptation はどんな手法ですか？", "alias", [["低ランク"], ["固定", "凍結"]])]),
    "temperature": ([["ランダム", "多様", "ばらつき"]],
                    [("LLMで次のトークンを選ぶときのランダムさを調整する設定値を何と呼びますか？", "reverse", [["temperature", "温度"]])]),
    "hallucination": ([["事実と異なる", "存在しない", "誤った", "間違った"]],
                      [("LLMが事実と異なる内容をもっともらしく生成してしまう現象を何と呼びますか？", "reverse", [["ハルシネーション", "幻覚"]])]),
    "mcp": ([["プロトコル"], ["ツール", "外部"]],
            [("Model Context Protocol について教えてください。", "alias", [["プロトコル"], ["ツール", "外部"]])]),
    "human-in-the-loop": ([["人"], ["承認", "確認"]],
                          [("エージェントの処理の途中に人の確認や承認を組み込むことを何と呼びますか？", "reverse",
                            [["Human-in-the-loop", "HITL", "ヒューマン・イン・ザ・ループ", "ヒューマンインザループ"]])]),
    "rate-limit": ([["一定時間", "回数", "リクエスト数"]],
                   [("APIで429エラーが返ってくるのはどんなときですか？", "alias", [["レート制限", "上限", "制限"]])]),
}

# 講座に固有らしいが、用語集に無い架空の用語。近い用語が用語集にあるものを混ぜている
UNKNOWN_COURSE = [
    "AIE2026の「宿題の5レベル」とは何ですか？",
    "「lecNN-end タグ」とは何ですか？",
    "「answer.yaml」とは何ですか？",
    "AIE2026の「週次リフレクションシート」とは何ですか？",
    "「Quriポイント」とは何ですか？",
]

# 用語集に無い一般的な用語
GENERAL = [
    ("「RAG」とは何ですか？", [["検索"]]),
    ("「Transformer」とは何ですか？", [["注意", "Attention", "アテンション"]]),
    ("「埋め込み（embedding）」とは何ですか？", [["ベクトル"]]),
    ("「Docker」とは何ですか？", [["コンテナ"]]),
    ("「勾配降下法」とは何ですか？", [["勾配"], ["最小", "小さく", "減ら"]]),
]

# 「分からない」と答えたとみなす語句（unknown_course の正解）
# 「ありません」だけだと「必要はありません」のような普通の文にも当たるので、具体的な言い回しに限る
REFUSAL_MARKERS = ["記載がありません", "記載されていません", "分かりません", "わかりません", "存在しません",
                   "情報がありません", "見つかりません", "確認できません", "知りません", "不明です"]


def main() -> None:
    terms = {t["id"]: t for t in json.loads(GLOSSARY.read_text(encoding="utf-8"))["terms"]}
    questions = []
    for tid, (seen_gold, paraphrases) in IN_GLOSSARY.items():
        term = terms[tid]["term"]
        questions.append({"category": "seen", "kind": "same_template", "term_id": tid,
                          "question": SFT_TEMPLATE.format(term=term), "must_include": seen_gold})
        for q, kind, gold in paraphrases:
            questions.append({"category": "paraphrase", "kind": kind, "term_id": tid, "question": q, "must_include": gold})
    for q in UNKNOWN_COURSE:
        questions.append({"category": "unknown_course", "kind": "fictional", "term_id": None, "question": q, "must_include": []})
    for q, gold in GENERAL:
        questions.append({"category": "general", "kind": "not_in_glossary", "term_id": None, "question": q, "must_include": gold})
    for i, q in enumerate(questions):
        q["id"] = f"q{i + 1:02d}"
    out = {"refusal_markers": REFUSAL_MARKERS, "questions": questions}
    sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
