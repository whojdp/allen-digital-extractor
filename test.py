import asyncio
from browser_use import Agent
from langchain_openai import ChatOpenAI

# This points to your LM Studio local server
llm = ChatOpenAI(
    base_url="http://localhost:1234/v1",
    api_key="lm-studio",
    model="qwen/qwen3.5-9b:2",
    temperature=0.0
)

async def main():
    agent = Agent(
        task="Go to google.com, search for 'JEE 2026 syllabus', tell me the first 3 results.",
        llm=llm,
    )
    result = await agent.run()
    print(result)

asyncio.run(main())