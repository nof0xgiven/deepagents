"""Test background task integration with the Textual app."""

import asyncio
from deepagents_cli.app import DeepAgentsApp
from deepagents_cli.background_tasks import BackgroundTaskManager
from deepagents_cli.textual_adapter import TextualUIAdapter, execute_task_textual
from deepagents_cli.widgets.agents_pill import AgentsPill
from deepagents_cli.widgets.subagent_panel import SubagentPanel
from langchain_core.messages import ToolMessage


async def test_pill_lifecycle():
    """Test that the agents pill shows/hides correctly with background tasks."""
    task_manager = BackgroundTaskManager()

    app = DeepAgentsApp(
        agent=None,
        task_manager=task_manager,
    )

    async with app.run_test(size=(120, 40), notifications=True) as pilot:
        pill = app.query_one("#agents-pill", AgentsPill)

        # Verify initial state
        assert pill.count == 0, f"Expected count=0, got {pill.count}"
        assert str(pill.styles.display) == "none", f"Expected display=none, got {pill.styles.display}"
        assert not pill.has_class("active"), "Pill should not have 'active' class initially"
        print("✅ [1] Initial state: pill hidden, count=0")

        # Verify callbacks registered
        assert len(task_manager._on_launch_callbacks) == 1
        assert len(task_manager._on_complete_callbacks) == 1
        print("✅ [2] Callbacks registered (1 launch, 1 complete)")

        # Launch task 1
        async def slow_handler(req):
            await asyncio.sleep(2)
            return ToolMessage(content="result 1", tool_call_id="tc1")

        tid1 = task_manager.generate_id("scout")
        task_manager._types[tid1] = "scout"
        task_manager.launch(tid1, slow_handler, None, description="scout task")
        await pilot.pause()
        await asyncio.sleep(0.1)
        await pilot.pause()

        assert pill.count == 1
        assert pill.has_class("active")
        print(f"✅ [3] After launch 1: pill shows '🤖 1 agent', count={pill.count}")

        # Launch task 2
        async def slow_handler2(req):
            await asyncio.sleep(3)
            return ToolMessage(content="result 2", tool_call_id="tc2")

        tid2 = task_manager.generate_id("worker")
        task_manager._types[tid2] = "worker"
        task_manager.launch(tid2, slow_handler2, None, description="worker task")
        await pilot.pause()
        await asyncio.sleep(0.1)
        await pilot.pause()

        assert pill.count == 2
        assert pill.has_class("active")
        print(f"✅ [4] After launch 2: pill shows '🤖 2 agents', count={pill.count}")

        # Wait for task 1 to complete
        await task_manager.wait(tid1)
        await pilot.pause()
        await asyncio.sleep(0.1)
        await pilot.pause()

        assert pill.count == 1
        assert pill.has_class("active")
        print(f"✅ [5] After task 1 completes: pill shows '🤖 1 agent', count={pill.count}")

        # Wait for task 2 to complete
        await task_manager.wait(tid2)
        await pilot.pause()
        await asyncio.sleep(0.1)
        await pilot.pause()

        assert pill.count == 0
        assert not pill.has_class("active")
        print(f"✅ [6] After task 2 completes: pill hidden, count={pill.count}")

        # Test cleanup
        async def long_handler(req):
            await asyncio.sleep(60)
            return ToolMessage(content="never", tool_call_id="tc3")

        tid3 = task_manager.generate_id("worker")
        task_manager._types[tid3] = "worker"
        task_manager.launch(tid3, long_handler, None, description="long task")
        await pilot.pause()
        await asyncio.sleep(0.1)
        await pilot.pause()

        assert pill.count == 1
        task_manager.cleanup()
        await pilot.pause()
        await asyncio.sleep(0.3)
        await pilot.pause()

        print(f"✅ [7] After cleanup: pill count={pill.count}")

        print("\n🎉 All tests passed!")


async def test_error_handling():
    """Test that failed tasks correctly decrement the pill."""
    task_manager = BackgroundTaskManager()

    app = DeepAgentsApp(
        agent=None,
        task_manager=task_manager,
    )

    async with app.run_test(size=(120, 40), notifications=True) as pilot:
        pill = app.query_one("#agents-pill", AgentsPill)

        async def failing_handler(req):
            await asyncio.sleep(1.5)
            raise RuntimeError("Something went wrong!")

        tid = task_manager.generate_id("worker")
        task_manager._types[tid] = "worker"
        task_manager.launch(tid, failing_handler, None, description="failing task")
        await pilot.pause()
        await asyncio.sleep(0.1)
        await pilot.pause()

        assert pill.count == 1
        print("✅ [E1] Failed task launched, pill count=1")

        await task_manager.wait(tid)
        await pilot.pause()
        await asyncio.sleep(0.1)
        await pilot.pause()

        assert pill.count == 0
        result = task_manager.check(tid)
        assert result["status"] == "failed"
        print(f"✅ [E2] Failed task completed, pill count=0, status={result['status']}")

        print("\n🎉 Error handling test passed!")


async def test_stream_namespace_tracking():
    """Test that streamed sub-agent namespace activity updates the pill."""
    app = DeepAgentsApp(
        agent=None,
        task_manager=None,
    )

    async with app.run_test(size=(120, 40), notifications=True) as pilot:
        pill = app.query_one("#agents-pill", AgentsPill)

        assert pill.count == 0

        # Simulate a streamed sub-agent namespace becoming active
        app._on_subagent_stream_start(("worker:abc123",))
        await pilot.pause()
        await asyncio.sleep(0.1)
        await pilot.pause()

        assert pill.count == 1
        assert pill.has_class("active")
        print("✅ [S1] Stream sub-agent start shows pill (count=1)")

        # Simulate background task launch while streamed sub-agent is still active
        app._on_background_task_launch("scout-1")
        await pilot.pause()
        await asyncio.sleep(0.1)
        await pilot.pause()

        assert pill.count == 1
        print("✅ [S2] Overlapping stream + background stays de-duplicated at 1")

        # Add a second streamed sub-agent namespace
        app._on_subagent_stream_start(("scout:xyz789",))
        await pilot.pause()
        await asyncio.sleep(0.1)
        await pilot.pause()

        assert pill.count == 2
        print("✅ [S3] Second independent stream namespace increases count to 2")

        # End streamed sub-agent first
        app._on_subagent_stream_end(("worker:abc123",))
        await pilot.pause()
        await asyncio.sleep(0.1)
        await pilot.pause()

        assert pill.count == 1
        print("✅ [S4] Ending one stream namespace decrements to 1")

        # Complete background task
        app._on_background_task_complete("scout-1", {"status": "completed", "duration": 0.1})
        await pilot.pause()
        await asyncio.sleep(0.1)
        await pilot.pause()

        assert pill.count == 1
        print("✅ [S5] Completing overlapping background task keeps remaining stream count at 1")

        # End final stream namespace
        app._on_subagent_stream_end(("scout:xyz789",))
        await pilot.pause()
        await asyncio.sleep(0.1)
        await pilot.pause()

        assert pill.count == 0
        assert not pill.has_class("active")
        print("✅ [S6] Ending final stream namespace hides pill (count=0)")


async def test_execute_task_emits_subagent_namespace_events():
    """Test execute_task_textual emits sub-agent namespace lifecycle callbacks."""

    class _SessionState:
        thread_id = "test-thread"
        auto_approve = False

    class _SubagentChunk:
        def __init__(self, chunk_position: str) -> None:
            self.chunk_position = chunk_position
            self.content_blocks = []
            self.usage_metadata = {}

    class _SubagentContentChunk:
        def __init__(self, chunk_position: str, text: str, include_tool: bool = False) -> None:
            self.chunk_position = chunk_position
            self.usage_metadata = {}
            self.content_blocks = [{"type": "text", "text": text}]
            if include_tool:
                self.content_blocks.append(
                    {
                        "type": "tool_call",
                        "name": "read_file",
                        "args": {"file_path": "/tmp/demo.txt"},
                        "id": "subagent-tool-1",
                    }
                )

    class _MainChunk:
        def __init__(self) -> None:
            self.content_blocks = []
            self.chunk_position = "last"
            self.usage_metadata = {}

    class _FakeAgent:
        async def astream(self, *_args, **_kwargs):
            yield (("worker",), "updates", {"worker": {"todos": [{"id": "1"}, {"id": "2"}]}})
            yield (("worker",), "messages", (_SubagentContentChunk("middle", "working", True), {}))
            yield (("worker",), "messages", (_SubagentContentChunk("last", " done"), {}))
            yield ((), "messages", (_MainChunk(), {}))

    async def _mount_message(_widget):
        return None

    async def _request_approval(_action_request, _assistant_id):
        raise RuntimeError("Approval should not be requested in this test")

    started: list[tuple] = []
    ended: list[tuple] = []
    text_updates: list[tuple[tuple, str]] = []
    tool_calls: list[tuple[tuple, str, dict]] = []
    updates: list[tuple[tuple, str]] = []

    adapter = TextualUIAdapter(
        mount_message=_mount_message,
        update_status=lambda _message: None,
        request_approval=_request_approval,
        on_subagent_start=lambda namespace: started.append(namespace),
        on_subagent_end=lambda namespace: ended.append(namespace),
        on_subagent_text=lambda namespace, text: text_updates.append((namespace, text)),
        on_subagent_tool_call=lambda namespace, name, args: tool_calls.append(
            (namespace, name, args)
        ),
        on_subagent_update=lambda namespace, status: updates.append((namespace, status)),
    )

    await execute_task_textual(
        user_input="run subagent",
        agent=_FakeAgent(),
        assistant_id=None,
        session_state=_SessionState(),
        adapter=adapter,
        backend=None,
    )

    assert started == [("worker",)]
    assert ended == [("worker",)]
    assert text_updates == [(("worker",), "working"), (("worker",), " done")]
    assert tool_calls == [
        (("worker",), "read_file", {"file_path": "/tmp/demo.txt"})
    ]
    assert updates == [(("worker",), "todo update: 2 item(s)")]
    print("✅ [S5] execute_task_textual emits sub-agent start/end callbacks")


async def test_subagent_panel_lifecycle():
    """Test subagent panel mount, stream updates, and cleanup in the app."""
    app = DeepAgentsApp(
        agent=None,
        task_manager=None,
    )

    async with app.run_test(size=(120, 40), notifications=True) as pilot:
        namespace = ("worker", "abc123")

        app._on_subagent_stream_start(namespace)
        await pilot.pause()
        await asyncio.sleep(0.1)
        await pilot.pause()

        panels = app.query(SubagentPanel)
        assert len(panels) == 1
        panel = panels.first()

        await app._on_subagent_stream_text(namespace, "hello from worker")
        await app._on_subagent_stream_tool_call(namespace, "read_file", {"file_path": "README.md"})
        await app._on_subagent_stream_update(namespace, "todo update: 1 item(s)")
        await pilot.pause()

        assert "hello from worker" in panel._content

        app._on_subagent_stream_end(namespace)
        await pilot.pause()
        await asyncio.sleep(0.1)
        await pilot.pause()

        assert len(app.query(SubagentPanel)) == 0
        print("✅ [S6] Subagent panel lifecycle mount/stream/cleanup works")


if __name__ == "__main__":
    print("=" * 60)
    print("Test 1: Pill lifecycle (launch, parallel, complete, cleanup)")
    print("=" * 60)
    asyncio.run(test_pill_lifecycle())

    print()
    print("=" * 60)
    print("Test 2: Error handling")
    print("=" * 60)
    asyncio.run(test_error_handling())

    print()
    print("=" * 60)
    print("Test 3: Stream namespace tracking")
    print("=" * 60)
    asyncio.run(test_stream_namespace_tracking())

    print()
    print("=" * 60)
    print("Test 4: execute_task_textual namespace callbacks")
    print("=" * 60)
    asyncio.run(test_execute_task_emits_subagent_namespace_events())

    print()
    print("=" * 60)
    print("Test 5: subagent panel lifecycle")
    print("=" * 60)
    asyncio.run(test_subagent_panel_lifecycle())
