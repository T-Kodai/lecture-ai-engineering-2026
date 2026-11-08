# 第3回 解答

実行環境：自分の Mac（Apple M5）。モデルは既定の `gemini-3.5-flash-lite`。APIキーは `.env`（git 管理外）から渡した。
コードの作成・実行と answer.md の下書きには Claude Code を使い、別のコーディングエージェント（Codex）のレビューを受けて直した。出力の原文は `results/` に残した。

## 演習

- 第1回（素のLLM）とエージェントの回答の違い：
  - 質問「AIE2026の講座の宿題にある「3レベル」とは何ですか？」
  - 第1回の `app.ask`：講座の情報は無いと前置きしたうえで、「基礎・初級 / 応用・中級 / 発展・上級」などの一般論を答えた（第1回の answer.md に記録）。
  - 第3回の `app.agent`：用語集を検索してから、「基礎（講義内容の確認）・実装（自分でコードを書く）・発展（調査や試行）」の 3 段階で「どれか1つに取り組めば完了、原則として採点しない」と、用語集の定義どおりに答え、最後に「関連する回：第1回」を付けた。
- `--trace` で見えたツール呼び出し（ツール名と引数）：[`results/exercise_step2_3.txt`](results/exercise_step2_3.txt)、[`results/exercise_make_quiz.txt`](results/exercise_make_quiz.txt)
  - 「3レベル」：`search_glossary({'query': '3レベル'})` の 1 回
  - 「LoRAとQLoRAの違いは？」：`search_glossary({'query': 'LoRA'})` と `search_glossary({'query': 'QLoRA'})` の 2 回。docstring の「query には調べたい用語を1つだけ入れる」のとおり、用語ごとに分けて検索した
  - 「第2回の内容から確認問題を1問出して」：`make_quiz({'lecture': 2})`
- 1つの質問での LLM 呼び出し回数（`requests`）：どの質問も 2 回（ツールを呼ぶと決める 1 回と、結果を見て答える 1 回）。
  「LoRAとQLoRA」は `tool_calls=2` でも `requests=2` だったので、2 つの検索は 1 回の応答でまとめて依頼されていた（講義のツールのバッチコール）。
- 追加したツールと、docstring に書いた説明：`make_quiz(lecture: int) -> str`（`app/tools.py`）を作り、`app/agent.py` で `agent.tool_plain(tools.make_quiz)` と登録した。
  - 中身：用語集から `lecture` が一致する用語を 1 つ選び、`{"question": "「○○」の意味は？", "answer": 定義, "lecture": 回}` を返す。用語が無い回（第0回・第5回など）では「用語がある回: 1, 2, 3, 4, 6」と返す。
  - docstring：「指定した回の用語から1つを選び、確認問題と答えを返す。『第2回の確認問題を出して』『復習用に1問出して』のように、復習のための問題を求められたときに使う。返した answer は用語集の定義なので、利用者が答えるまで見せず、答え合わせに使うこと。」
  - 確かめたこと：`--list-tools` に docstring ごと表示された（[`results/exercise_list_tools.txt`](results/exercise_list_tools.txt)）。`--trace` で `make_quiz({'lecture': 2})` が呼ばれ、問題だけを出して答えは伏せた。`uv run pytest -q` は 15 passed。
    答えを伏せたのが docstring の一文の効果かは、書かない場合と比べていないので分からない。

## 宿題

- 取り組んだレベル：**発展（a）**（ADK で作り直す）
- やったこと：
  - [`adk_agent/glossary_agent/agent.py`](../../adk_agent/glossary_agent/agent.py) と `__init__.py` を作った。指示は `app.agent` の `INSTRUCTIONS`、ツールは `app/tools.py` の `search_glossary`・`get_lecture_summary`・`make_quiz` をそのまま使い、`app/` 側は変えていない。ADK は 2.14.0。
  - `PYTHONPATH=. uv run --with google-adk adk run adk_agent/glossary_agent` で動くことを確かめた。
  - 比べるために [`scripts/compare_lec03.py`](../../scripts/compare_lec03.py) を作り、演習と同じ 3 問を、Pydantic AI 版（`app.agent`）と ADK 版（`adk run --replay`）にそれぞれ 3 回ずつ投げた（毎回新しい会話）。
    ADK 版のツール呼び出しは、`--save_session` で保存したセッションの記録から読んだ。生データは [`results/compare.jsonl`](results/compare.jsonl) と [`results/adk_sessions/`](results/adk_sessions/)。
- 結果：

  **書き方の違い**

  | 観点 | Pydantic AI（`app/agent.py`） | ADK（`adk_agent/glossary_agent/agent.py`） |
  | --- | --- | --- |
  | 指示 | `Agent(instructions=INSTRUCTIONS)` | `Agent(instruction=INSTRUCTIONS)`（引数名が単数形） |
  | ツール | `agent.tool_plain(関数)` を 1 つずつ呼んで登録 | `tools=[関数, …]` でまとめて渡す。どちらも関数の docstring と型ヒントからツールの説明を作る |
  | モデル | 実行時に `run_sync(..., model=GoogleModel(...))` で渡す（テストで `TestModel` に差し替えられる） | 定義の中に `model="gemini-3.5-flash-lite"` と文字列で書く（資料のとおり書いたので、`AIE_MODEL` での切り替えは効かない） |
  | APIキー | `app.config.get_api_key()` で `GEMINI_API_KEY` を明示的に読む | 環境変数から自動で読む（`GEMINI_API_KEY` だけで動いた） |
  | 名前 | 不要 | `name` が必須（省くと検証エラー） |
  | 実行と記録 | 自作の CLI（`app.agent`、`--trace` で呼び出しを表示） | `adk run`（対話、`--replay`、`--save_session`）。会話は既定でエージェントのフォルダの `.adk/session.db` に保存される |

  **同じ 3 問を 3 回ずつ投げた結果**

  | 質問 | 呼ばれたツール（両方とも 3 回すべて同じ） | requests | 入力トークン（Pydantic AI → ADK） | 出力トークン（同） |
  | --- | --- | --- | --- | --- |
  | 3レベル | `search_glossary('3レベル')` | 両方 2 | 1013 → 1139 | 107〜146 / 113〜168 |
  | LoRAとQLoRA | `search_glossary('LoRA')`、`search_glossary('QLoRA')` | 両方 2 | 1426 → 1550 | 184〜221 / 159〜184 |
  | 確認問題 | `make_quiz(2)` | 両方 2 | 951〜987 → 1077〜1120 | 68〜69 / 59〜68 |

  - ツールの選び方・引数・回数・LLM の呼び出し回数は、9 組すべてで同じだった。
  - 回答の中身も同等だった。3レベルは 6 回とも 3 段階と「どれか1つで完了」を含み、LoRA/QLoRA は 6 回とも「重みを固定」「4 ビットに量子化」を含んだ。確認問題は 6 回とも問題だけを出し、答え（定義）は見せなかった。全 18 回の回答の最後に関係する回が付いた。
  - 違いは入力トークンで、ADK 版が 3レベルでは毎回 126、LoRA/QLoRA では毎回 124 トークン多かった（同じ質問なら 3 回とも同じ値）。
    確認問題は選ばれる用語が毎回違い、ツールが返す文の長さも変わるので、差も 90〜165 とばらついた。
    ADK のデバッグログで実際の送信内容を見ると、ADK は `INSTRUCTIONS` の後ろに `You are an agent. Your internal name is "glossary_agent".` という 1 文を自動で足していた。ツールの引数の定義にも、Pydantic AI には無い `title`（例：`search_glossaryParams`）が付いていた。これらが差の一部と考えられるが、124〜126 トークンの内訳までは数えていない。
  - 応答時間は ADK 版が約 2 秒長かったが、`adk run` を毎回起動する時間を含むので、エージェント自体の速さの比較にはならない。
- 気づき・疑問：
  - 同じモデル・同じ指示・同じツールなら、組み立てる道具を替えても、今回の質問ではふるまいは変わらなかった。違いが出たのは、道具の側が足す「見えない指示」とツールの定義の書き方で、そのぶん毎回のリクエストの入力が約 1 割増えた。講義の「ハーネスで費用と速さが変わる」「ユーザーに見えない指示も毎回一緒に送っている」を、小さな形で確かめられた。
  - ADK は会話を既定でファイル（`.adk/session.db`）に保存する。続きから話せる便利さの一方、何がどこに残るかを把握しておく必要がある（講義のメモリと信頼境界の話）。`.gitignore` に `.adk/` を足した。
  - 確認問題の用語は `make_quiz` が毎回ランダムに選ぶので、Pydantic AI 版と ADK 版で出た問題は違う。比べたのは「答えを伏せたか」などのふるまいで、問題の中身ではない。
  - 限界：各 3 回・3 問だけで、どれもツールが 1〜2 回で済む簡単な質問。ツール選びが難しい質問（使うべきツールが曖昧なもの、用語集に無いもの）では差が出るかもしれない。
