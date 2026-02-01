from __future__ import annotations

import asyncio

from src.agents.tracking import SMSAAIAssistantTrackingAgent


def test_tracking_agent_extracts_awb_and_returns_content() -> None:
    agent = SMSAAIAssistantTrackingAgent()
    ctx = {"message": "Please track AWB 227047923763"}

    async def _run():
        res = await agent.run(ctx)
        assert res["agent"] == "tracking"
        assert "227047923763" in res["content"]
        assert res["results"]

    asyncio.run(_run())

