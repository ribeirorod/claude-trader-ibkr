import json
import uuid
from pathlib import Path
import pytest
from trader.agents.log import AgentLog, LogEvent


@pytest.fixture
def log_file(tmp_path):
    return tmp_path / "agent.jsonl"


def test_write_single_event(log_file):
    log = AgentLog(log_file)
    log.write(LogEvent(
        run_id="run-1",
        agent="conductor",
        event="RUN_START",
        data={"time_slot": "pre-market"},
    ))
    lines = log_file.read_text().strip().split("\n")
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["run_id"] == "run-1"
    assert entry["agent"] == "conductor"
    assert entry["event"] == "RUN_START"
    assert entry["context"]["time_slot"] == "pre-market"
    assert "ts" in entry


def test_write_multiple_events(log_file):
    log = AgentLog(log_file)
    for i in range(3):
        log.write(LogEvent(run_id="run-1", agent="conductor", event=f"EVENT_{i}", data={}))
    lines = log_file.read_text().strip().split("\n")
    assert len(lines) == 3


def test_read_last_n(log_file):
    log = AgentLog(log_file)
    for i in range(10):
        log.write(LogEvent(run_id="r", agent="a", event=f"E{i}", data={"i": i}))
    last5 = log.read_last(5)
    assert len(last5) == 5
    assert last5[-1]["context"]["i"] == 9
    assert last5[0]["context"]["i"] == 5


def test_read_last_n_fewer_than_n_entries(log_file):
    log = AgentLog(log_file)
    log.write(LogEvent(run_id="r", agent="a", event="E0", data={}))
    result = log.read_last(50)
    assert len(result) == 1


def test_read_last_empty_file(log_file):
    log = AgentLog(log_file)
    result = log.read_last(10)
    assert result == []


def test_new_run_id_is_unique():
    id1 = AgentLog.new_run_id()
    id2 = AgentLog.new_run_id()
    assert id1 != id2
    assert len(id1) == 8  # short hex prefix
