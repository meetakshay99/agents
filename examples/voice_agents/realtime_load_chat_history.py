import logging

from dotenv import load_dotenv

from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, cli, llm
from livekit.plugins import openai

## This example shows how to load chat history for OpenAI Realtime Model

logger = logging.getLogger("realtime-load-chat-history")

load_dotenv()


async def entrypoint(ctx: JobContext):
    chat_history = [
        {
            "role": "assistant",
            "content": "Hello, I am a travel planner. How can I help you?",
        },
        {
            "role": "user",
            "content": "I want to go to Paris this summer.",
        },
        {
            "role": "assistant",
            "content": "Paris is a beautiful city. How many days will you be staying?",
        },
        {
            "role": "user",
            "content": "I'll have four days. What are the main attractions I should see?",
        },
    ]

    chat_ctx = llm.ChatContext.empty()
    for item in chat_history:
        chat_ctx.add_message(role=item["role"], content=item["content"])

    session = AgentSession()
    agent = Agent(
        instructions="You are a helpful travel planner.",
        llm=openai.realtime.RealtimeModel(modalities=["text"]),
        # OpenAI realtime API may response in only text when text-based chat context is loaded
        # so we recommend to use text modality with a TTS model when chat history is needed
        # more details about this issue: https://community.openai.com/t/trouble-loading-previous-messages-with-realtime-api
        tts=openai.TTS(voice="alloy"),
        chat_ctx=chat_ctx,
    )

    await session.start(agent=agent, room=ctx.room)

    logger.info("Generating reply...")
    session.interrupt()
    session.generate_reply()


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
