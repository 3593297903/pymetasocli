import asyncio
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from metasocli_py.video import execution


@pytest.mark.asyncio
async def test_delayed_wakeup_does_not_start_another_history_round(tmp_path, monkeypatch):
    clock = [0.0]
    query_starts = []

    async def query(*_args, **_kwargs):
        query_starts.append(clock[0])
        clock[0] += 0.01
        return 'running'

    async def delayed_wakeup(_seconds):
        clock[0] = 0.2

    monkeypatch.setattr(execution, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(execution, 'lock', lambda *_a, **_kw: nullcontext())
    monkeypatch.setattr(execution, 'observe_once', query)
    monkeypatch.setattr(execution.asyncio, 'sleep', delayed_wakeup)
    changed = asyncio.Event()
    await execution.observe_history(
        tmp_path, {'operationId': 'synthetic'}, SimpleNamespace(root=tmp_path), None,
        asyncio.Semaphore(4), execution.ExecutionOptions(
            max_polls=3, capacity_wait=0.1, poll_seconds=0.01),
        changed, [object()], [],
    )
    assert query_starts == [0.0]
    assert changed.is_set()
