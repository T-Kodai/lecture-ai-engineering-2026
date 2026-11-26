# 第6回 解答

## 演習

<!-- [tool call] の行は、表示された行をそのまま貼り付けてください。終わらなかった STEP は、空欄のままでかまいません。 -->

- STEP 1 のツールの名前：`glossary_search_glossary`
- STEP 2 の [tool call]：`glossary_search_glossary({'query': '3レベル'})`
- STEP 3 の [tool call]：`fetch_fetch({'url': 'https://modelcontextprotocol.io/'})`
- STEP 4 の [tool call]：`aws_aws___search_documentation({'topics': ['general'], 'search_phrase': 'Amazon S3 versioning overview'})`
- 気づき・疑問：
  - fetch サーバーのツール説明文に、「元はインターネットにアクセスできなかったが、このツールでアクセスできるようになった」という、モデルに向けた文が入っていた。説明文はそのままモデルに渡るので、サーバーを足すときは説明文も読んでおく必要があると思った。
  - fetch はページを取る前に `robots.txt` を取得していた（STEP 3 のログ）。演習資料の補足にある既定の動作のとおり。
  - 入力は STEP 2〜4 で 715 → 2,232 → 6,359 トークン、モデルに見えるツールは 1 → 2 → 7 個だった。質問も違うので、増えた分の内訳は測っていない。

モデルは `gemini-3.5-flash-lite`。表示はすべて `results/exercise/` に保存した。

## 宿題

<!-- 基礎・実装・発展のどれか1つに取り組めば完了です。 -->

- 取り組んだレベル：発展
- やったこと：
  - Claude Code（手元の版は 2.1.323）を選び、MCP サーバーの設定方法を調べて、演習の `app/mcp_servers.json` と比べた。
    参照したのは公式ドキュメント「Connect Claude Code to tools via MCP」（https://code.claude.com/docs/en/mcp 、日本語版 https://code.claude.com/docs/ja/mcp 、2026-11-26 に確認）と、`claude mcp add --help` の表示。
  - 調べた内容を確かめるため、演習（STEP 4 まで）の設定ファイルを Claude Code に一時的に読み込ませた。
    `claude -p --mcp-config <設定ファイル> --strict-mcp-config` で起動し、起動時に接続したサーバーと登録されたツールを記録した。普段登録している MCP サーバーは読み込ませず、`claude mcp add` などによる登録もしていない。
    スクリプトは `scripts/check_claude_code_mcp_lec06.py`、結果は `results/homework/claude_code_mcp_check.json`。
- 結果：

  | 調べること | 演習（`app/mcp_servers.json`） | Claude Code |
  |---|---|---|
  | 設定を書く場所 | `app/mcp_servers.json`（`app/mcp_agent.py` がこのパスを読む） | 共有する設定はプロジェクト直下の `.mcp.json`、自分だけの設定は `~/.claude.json`。ふつうは `claude mcp add` か `claude mcp add-json` で書き込む。1 回だけなら起動時に `--mcp-config` でファイルを渡せる |
  | コマンドで起動する書き方 | `"command"` と `"args"`（`"env"` も読む） | 同じく `command`・`args`・`env`。`"type": "stdio"` は省略できる。コマンドでは `claude mcp add <名前> -- <コマンド> <引数>` |
  | URL で接続する書き方 | `"url"` だけ | `"url"` と、接続方式の `"type"`（今回の AWS は `"http"`）の両方が必要。`type` がないと、その設定は読み込まれない。認証用の `headers` も書ける。コマンドでは `claude mcp add --transport http <名前> <URL>`（SSE は非推奨） |
  | 有効になる範囲 | このリポジトリの `mcp_agent` だけ。ファイルはリポジトリに入っているので、Claude Code の project と同じく git で共有される | 3 段階。local（既定。そのプロジェクトで自分だけ）、project（そのプロジェクトで、`.mcp.json` を git で共有）、user（自分のすべてのプロジェクト）。同じ名前があれば local → project → user の順に優先し、項目どうしは合わせない |
  | ツールの名前（参考） | `glossary_search_glossary` | `mcp__glossary__search_glossary` |

  一時的に読み込ませた結果：
  - 演習の設定をそのまま渡すと、glossary と fetch は接続し、aws は読み込まれなかった。エラーは `Skipped — MCP server "aws" has a "url" but no "type"; add "type": "http" (or "sse" / "ws") to this entry`。ドキュメントの記述どおりだった。
  - aws に `"type": "http"` を足すと（`results/homework/mcp_servers_claude_code.json`）、3 つとも接続し、MCP のツールが 7 個登録された。同じファイルを演習のエージェントで読んでも、7 個のツールが表示された（`results/homework/mcp_agent_list_tools_with_type.txt`）。
  - 確かめたのは、起動時の接続とツールの登録まで。`claude mcp add` や `.mcp.json` による登録は、ドキュメントで調べただけで実行していない。
- 気づき・疑問：
  - 同じ `"mcpServers"` の形でも、URL の書き方はソフトによって違った。設定を別のソフトに写したときは、全部のサーバーがつながったかを確かめる必要がある。`"type": "http"` を足した形なら、今回は両方で動いた。
  - ドキュメントによると、`.mcp.json` のサーバーは、対話で使うときは使う前に承認を求められる。一方、`claude -p` では承認なしで読み込まれる。リポジトリに置いた設定でコマンドが起動するので、他人のリポジトリで `-p` を使うときは、先に `.mcp.json` を見ておいたほうがよいと思った（今回のように `--strict-mcp-config` で読み込みを絞る方法もある）。
