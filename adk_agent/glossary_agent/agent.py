"""第3回 宿題（発展 a）: 演習のエージェントを、組み立て部分だけ Google ADK で書き直したもの。

指示（INSTRUCTIONS）とツール（app/tools.py の関数）は演習とまったく同じものを使う。
動かし方（リポジトリの直下で）:
    PYTHONPATH=. uv run --with google-adk adk run adk_agent/glossary_agent
"""

from google.adk.agents import Agent

from app import tools
from app.agent import INSTRUCTIONS

root_agent = Agent(
    model="gemini-3.5-flash-lite",
    name="glossary_agent",
    instruction=INSTRUCTIONS,
    # ADK は Python の関数をそのまま渡すと、docstring と型ヒントからツールの説明を作る（Pydantic AI の tool_plain と同じ考え方）
    tools=[tools.search_glossary, tools.get_lecture_summary, tools.make_quiz],
)
