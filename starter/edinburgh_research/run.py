"""Ex5 — Edinburgh research scenario entrypoint.

Usage:
    make ex5            # offline, FakeLLMClient
    make ex5-real       # uses Nebius (burns tokens)

What's different from a pure scaffold:
  * `Config.from_env()` is used for --real mode so your `.env` models win
  * `example_sessions_dir()` gives us tempdir-offline, persistent-real
  * A preflight checks whether your TODOs are implemented and prints
    a friendly message instead of letting the framework crash cryptically
"""

from __future__ import annotations

import asyncio
import json
import sys

from sovereign_agent._internal.llm_client import (
    FakeLLMClient,
    OpenAICompatibleClient,
    ScriptedResponse,
    ToolCall,
)
from sovereign_agent._internal.paths import example_sessions_dir
from sovereign_agent.executor import DefaultExecutor
from sovereign_agent.halves.loop import LoopHalf
from sovereign_agent.planner import DefaultPlanner
from sovereign_agent.session.directory import create_session
from sovereign_agent.tickets.ticket import list_tickets

from starter.edinburgh_research.integrity import clear_log, verify_dataflow
from starter.edinburgh_research.tools import build_tool_registry


def _build_fake_client() -> FakeLLMClient:
    """Scripts a 2-subgoal trajectory for offline mode. Keep one call
    per tool so the integrity check has data to verify."""
    plan_json = json.dumps(
        [
            {
                "id": "sg_1",
                "description": "research Edinburgh venues near Haymarket for a party of 6",
                "success_criterion": "at least one candidate identified",
                "estimated_tool_calls": 3,
                "depends_on": [],
                "assigned_half": "loop",
            },
            {
                "id": "sg_2",
                "description": "produce a flyer with the chosen venue, weather, and cost",
                "success_criterion": "flyer.md written to workspace/",
                "estimated_tool_calls": 1,
                "depends_on": ["sg_1"],
                "assigned_half": "loop",
            },
        ]
    )
    search_call = ToolCall(
        id="c1",
        name="venue_search",
        arguments={"near": "Haymarket", "party_size": 6, "budget_max_gbp": 800},
    )
    weather_call = ToolCall(
        id="c2", name="get_weather", arguments={"city": "edinburgh", "date": "2026-04-25"}
    )
    cost_call = ToolCall(
        id="c3",
        name="calculate_cost",
        arguments={
            "venue_id": "haymarket_tap",
            "party_size": 6,
            "duration_hours": 3,
            "catering_tier": "bar_snacks",
        },
    )
    flyer_call = ToolCall(
        id="c4",
        name="generate_flyer",
        arguments={
            "event_details": {
                "venue_name": "Haymarket Tap",
                "venue_address": "12 Dalry Rd, Edinburgh EH11 2BG",
                "date": "2026-04-25",
                "time": "19:30",
                "party_size": 6,
                "condition": "cloudy",
                "temperature_c": 12,
                "total_gbp": 540,
                "deposit_required_gbp": 0,
            }
        },
    )
    complete_call = ToolCall(
        id="c5",
        name="complete_task",
        arguments={"result": {"flyer": "workspace/flyer.md", "venue": "haymarket_tap"}},
    )

    return FakeLLMClient(
        [
            ScriptedResponse(content=plan_json),
            ScriptedResponse(tool_calls=[search_call, weather_call, cost_call]),
            ScriptedResponse(tool_calls=[flyer_call]),
            ScriptedResponse(tool_calls=[complete_call]),
            ScriptedResponse(content="Subgoal 1 complete."),
            ScriptedResponse(content="Booking researched; flyer at workspace/flyer.md."),
            ScriptedResponse(content="Task complete."),
        ]
    )


def _tools_are_implemented() -> tuple[bool, str]:
    """Probe tool modules for NotImplementedError. Returns (ok, message)."""
    from starter.edinburgh_research.tools import (
        calculate_cost,
        generate_flyer,
        get_weather,
        venue_search,
    )

    unimplemented: list[str] = []
    for name, call in [
        ("venue_search", lambda: venue_search("Haymarket", 6, 1000)),
        ("get_weather", lambda: get_weather("edinburgh", "2026-04-25")),
        ("calculate_cost", lambda: calculate_cost("haymarket_tap", 6, 3)),
    ]:
        try:
            call()
        except NotImplementedError:
            unimplemented.append(name)
        except Exception:
            pass  # any other exception = student has done SOME work

    import inspect

    try:
        src = inspect.getsource(generate_flyer)
        if "raise NotImplementedError" in src and src.count("\n") < 30:
            unimplemented.append("generate_flyer")
    except (OSError, TypeError):
        pass

    try:
        from starter.edinburgh_research.integrity import verify_dataflow as _vd

        src = inspect.getsource(_vd)
        if "raise NotImplementedError" in src and src.count("\n") < 60:
            unimplemented.append("verify_dataflow")
    except (OSError, TypeError, ImportError):
        pass

    if not unimplemented:
        return True, ""

    msg = "\n".join(
        [
            "",
            "━" * 72,
            "  Ex5 isn't implemented yet — expected for a fresh checkout.",
            "━" * 72,
            "",
            f"  Unimplemented: {', '.join(unimplemented)}",
            "",
            "  What to do:",
            "    1. Open starter/edinburgh_research/tools.py",
            "    2. Implement each function marked `TODO` in order: venue_search,",
            "       get_weather, calculate_cost, generate_flyer.",
            "    3. Open starter/edinburgh_research/integrity.py and implement",
            "       verify_dataflow (the heart of Ex5's grade).",
            "    4. Run `make test` — aim to turn the 3 skipped tests green.",
            "    5. Run `make ex5` again.",
            "",
            "  Reference pattern: examples/pub_booking/run.py in the sovereign-agent",
            "  repo has a similar structure (loop half, parallel-safe reads, one",
            "  file write). Copy patterns, change the scenario.",
            "",
            "━" * 72,
            "",
        ]
    )
    return False, msg


async def run_scenario(real: bool) -> int:
    clear_log()

    ok, message = _tools_are_implemented()
    if not ok:
        print(message)
        return 3

    with example_sessions_dir("ex5-edinburgh-research", persist=real) as sessions_root:
        session = create_session(
            scenario="edinburgh-research",
            task=(
                "Find an Edinburgh pub near Haymarket for a party of 6 on "
                "2026-04-25 at 19:30. Check the weather, work out the catering "
                "cost, and write a flyer to workspace/flyer.md."
            ),
            sessions_dir=sessions_root,
        )
        print(f"Session {session.session_id}")
        print(f"  dir: {session.directory}")

        if real:
            from sovereign_agent.config import Config

            cfg = Config.from_env()
            print(f"  LLM: {cfg.llm_base_url} (live)")
            print(f"  planner:  {cfg.llm_planner_model}")
            print(f"  executor: {cfg.llm_executor_model}")
            client = OpenAICompatibleClient(
                base_url=cfg.llm_base_url,
                api_key_env=cfg.llm_api_key_env,
            )
            planner_model = cfg.llm_planner_model
            executor_model = cfg.llm_executor_model
        else:
            print("  LLM: FakeLLMClient (offline, scripted)")
            client = _build_fake_client()
            planner_model = executor_model = "fake"

        tools = build_tool_registry(session)
        half = LoopHalf(
            planner=DefaultPlanner(model=planner_model, client=client),
            executor=DefaultExecutor(model=executor_model, client=client, tools=tools),  # type: ignore[arg-type]
        )

        result = await half.run(session, {"task": "research Edinburgh venue and write flyer"})
        print(f"\nLoop half outcome: {result.next_action}")
        print(f"  summary: {result.summary}")

        print("\nTickets:")
        for t in list_tickets(session):
            r = t.read_result()
            print(f"  {t.ticket_id}  {t.operation:50s}  {r.state.value}")

        flyer_path = session.workspace_dir / "flyer.md"
        if not flyer_path.exists():
            print("\n✗ No flyer written to workspace/. Ex5 failed.")
            return 1

        print(f"\n=== flyer.md ({flyer_path.stat().st_size} bytes) ===")
        flyer_content = flyer_path.read_text(encoding="utf-8")
        print(flyer_content[:500] + ("...\n[truncated]" if len(flyer_content) > 500 else ""))

        print("\n=== Dataflow integrity check ===")
        integrity = verify_dataflow(flyer_content)
        if integrity.ok:
            print(f"✓  {integrity.summary}")
            if integrity.verified_facts:
                print(f"   Verified {len(integrity.verified_facts)} fact(s) against tool outputs.")
        else:
            print(f"✗  {integrity.summary}")
            print(f"   Unverified facts: {integrity.unverified_facts}")
            return 2

        if real:
            print(f"\nArtifacts persist at: {session.directory}")
            print(f'Inspect with: ls -R "{session.directory}"')

        return 0


def main() -> None:
    real = "--real" in sys.argv
    sys.exit(asyncio.run(run_scenario(real=real)))


if __name__ == "__main__":
    main()
