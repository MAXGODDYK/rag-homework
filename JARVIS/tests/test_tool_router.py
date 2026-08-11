from __future__ import annotations

import pytest

from scripts.rag.providers import ProviderError
from scripts.tools.router import ToolRouter, is_exchange_rate_candidate
from scripts.tools.schemas import ToolRoutingError


class FakeProvider:
    def __init__(
        self,
        outputs: list[str],
        available: bool = True,
        fail: bool = False,
    ) -> None:
        self.outputs = outputs
        self.available = available
        self.fail = fail
        self.calls = 0

    def availability(self) -> tuple[bool, str]:
        return self.available, "test unavailable"

    def generate(self, prompt: str) -> str:
        self.calls += 1
        if self.fail:
            raise ProviderError("private provider error")
        return self.outputs.pop(0)


def _tool_json() -> str:
    return (
        '{"action":"tool","tool_name":"get_nbu_exchange_rate",'
        '"arguments":{"currency_code":"eur","date":null,"amount":100}}'
    )


def test_prefilter_and_rag_decision_do_not_call_tool_router_unnecessarily() -> None:
    provider = FakeProvider([])
    router = ToolRouter({"freemodel": provider})

    outcome = router.route("Як скласти план навчання?", "freemodel")

    assert not is_exchange_rate_candidate("Як скласти план навчання?")
    assert outcome.decision.action == "rag"
    assert outcome.provider_name == "prefilter"
    assert provider.calls == 0


def test_router_accepts_allowlisted_tool_and_rag_contracts() -> None:
    provider = FakeProvider(
        [
            _tool_json(),
            '{"action":"rag","tool_name":null,"arguments":null}',
        ]
    )
    router = ToolRouter({"freemodel": provider})

    tool = router.route("Скільки гривень потрібно для 100 EUR?", "freemodel")
    rag = router.route("Що таке валютний ризик?", "freemodel")

    assert tool.decision.action == "tool"
    assert tool.decision.arguments.currency_code == "EUR"
    assert rag.decision.action == "rag"


def test_router_repairs_once_then_fails_safely() -> None:
    repair_provider = FakeProvider(["not json", _tool_json()])
    repaired = ToolRouter({"freemodel": repair_provider}).route(
        "Курс EUR сьогодні",
        "freemodel",
    )
    assert repaired.decision.action == "tool"
    assert repair_provider.calls == 2

    invalid_provider = FakeProvider(["bad", "still bad"])
    with pytest.raises(ToolRoutingError, match="/rate"):
        ToolRouter({"freemodel": invalid_provider}).route(
            "Курс USD сьогодні",
            "freemodel",
        )
    assert invalid_provider.calls == 2


def test_remote_router_falls_back_to_local() -> None:
    remote = FakeProvider([], available=False)
    local = FakeProvider([_tool_json()])

    outcome = ToolRouter(
        {"freemodel": remote, "local": local}
    ).route("Exchange rate for EUR", "freemodel")

    assert outcome.provider_name == "local"
    assert outcome.notice is not None
    assert local.calls == 1
