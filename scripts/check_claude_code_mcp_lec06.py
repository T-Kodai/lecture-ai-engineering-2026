"""第6回 宿題（発展）: 演習の MCP 設定を Claude Code に一時的に読み込ませ、接続とツール一覧を確かめる。

使い方（リポジトリの直下で）:
    uv run python -m scripts.check_claude_code_mcp_lec06

- `claude -p --mcp-config <設定> --strict-mcp-config` で 1 回ずつ起動する。
  普段登録している MCP サーバー（~/.claude.json や .mcp.json）は読み込まない。登録（claude mcp add）もしない。
  セッションも保存しない（--no-session-persistence）。
- 起動時の system/init イベントから、サーバーの接続状態・登録された MCP ツール・読み飛ばされた設定だけを
  取り出して保存する（パスやセッション ID などは保存しない）。確かめるのは起動時の接続とツール一覧まで。
"""

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "lectures" / "06" / "results" / "homework"
CONFIGS = {
    # 演習（STEP 4 まで）の設定ファイルをそのまま渡す
    "as_is": REPO / "app" / "mcp_servers.json",
    # aws に "type": "http" を足しただけの設定
    "with_type": OUT_DIR / "mcp_servers_claude_code.json",
}
PROMPT = "接続テストです。ツールは使わず「OK」とだけ返してください。"


def check(config: Path) -> dict:
    cmd = [
        "claude", "-p",
        "--mcp-config", str(config), "--strict-mcp-config",
        "--no-session-persistence",
        "--output-format", "stream-json", "--verbose",
        "--model", "haiku", "--max-turns", "1",
        PROMPT,
    ]
    # claude.ai のコネクタも読み込まないようにする（このスクリプトの子プロセスだけ）
    env = {**os.environ, "ENABLE_CLAUDEAI_MCP_SERVERS": "false"}
    proc = subprocess.run(
        cmd, cwd=REPO, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300
    )
    for line in proc.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            return {
                "config": str(config.relative_to(REPO)),
                "claude_code_version": event.get("claude_code_version"),
                "mcp_servers": [{"name": s["name"], "status": s["status"]} for s in event.get("mcp_servers", [])],
                "mcp_tools": sorted(t for t in event.get("tools", []) if t.startswith("mcp__")),
                "mcp_server_errors": event.get("mcp_server_errors") or [],
            }
    raise SystemExit(f"init イベントが見つかりませんでした: {proc.stderr[:500]}")


def main() -> None:
    result = {"checked_at": datetime.now().isoformat(timespec="seconds"), "runs": {}}
    for name, config in CONFIGS.items():
        result["runs"][name] = check(config)
    out = OUT_DIR / "claude_code_mcp_check.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
