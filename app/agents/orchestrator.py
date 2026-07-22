"""
LangGraph Multi-Agent Orchestrator.

Architecture:
  User message → Supervisor (router) → Sub-agent node → Response

The supervisor classifies intent and routes to the correct specialist agent.
Each agent runs its agentic loop (tool calls → final response).
State is persisted to PostgreSQL via LangGraph checkpointing.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.agents.bank_reconciliation import BankReconciliationAgent
from app.agents.controller import ControllerAgent
from app.agents.eod_report import EODReportAgent
from app.agents.grant_compliance import GrantComplianceAgent
from app.agents.payment_request import PaymentRequestAgent
from app.agents.payroll_allocation import PayrollAllocationAgent
from app.agents.qbo_auditor import QBOAuditorAgent
from app.agents.sop_builder import SOPBuilderAgent
from app.agents.transaction_coder import TransactionCoderAgent
from app.agents.vendor_onboarding import VendorOnboardingAgent
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

# ── Graph State ───────────────────────────────────────────────────────────────

AgentNode = Literal[
    "qbo_auditor",
    "transaction_coder",
    "grant_compliance",
    "payment_request",
    "vendor_onboarding",
    "sop_builder",
    "eod_report",
    "controller",
    "bank_reconciliation",
    "payroll_allocation",
    "__end__",
]


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    active_module: str
    qbo_realm_id: str | None
    context: dict[str, Any]
    tool_calls_made: list[str]


# ── Router LLM ────────────────────────────────────────────────────────────────

_ROUTER_SYSTEM = """
You are a routing classifier for a Finance Operations AI system.
Given a user message, identify which specialist module should handle it.

Modules:
- qbo_auditor: Auditing QBO files, reviewing reports, finding accounting errors, audit findings
- transaction_coder: Categorizing transactions, coding bank feeds, CSV/Excel imports, uncategorized expenses
- grant_compliance: Grant audits, grant compliance, nonprofit fund accounting, restricted funds
- payment_request: Processing bills, verifying invoices, payment approvals, AP documentation
- vendor_onboarding: New vendor setup, W-9, ACH, vendor documentation, vendor checklist
- sop_builder: Creating SOPs, documenting processes, accounting procedures, workflow documentation
- eod_report: End of day reports, daily summaries, work logs, what did I do today
- controller: Controller review, financial dashboards, month-end close, morning briefing, financial analysis
- bank_reconciliation: Bank reconciliation, credit card reconciliation, conciliacion de bancos, uncleared items, outstanding checks, deposits in transit, reconciling differences
- payroll_allocation: Payroll analysis, payroll desglose, payroll breakdown, salary allocation, payroll journal entries, employee payroll, FTE allocation, payroll taxes, deductions, payroll compliance

Respond with ONLY the module name. No explanation.
"""


class FinanceOrchestrator:
    """
    LangGraph-based multi-agent orchestrator.
    Routes messages to the appropriate specialist agent and returns responses.
    """

    def __init__(self, qbo_tools: list[BaseTool] | None = None) -> None:
        self._qbo_tools = qbo_tools or []
        self._router_llm = ChatAnthropic(
            model=settings.anthropic_model,
            max_tokens=256,
            api_key=settings.anthropic_api_key,
        )

        # Instantiate all 10 specialist agents
        self._agents: dict[str, Any] = {
            "qbo_auditor": QBOAuditorAgent(qbo_tools=self._qbo_tools),
            "transaction_coder": TransactionCoderAgent(extra_tools=self._qbo_tools),
            "grant_compliance": GrantComplianceAgent(qbo_tools=self._qbo_tools),
            "payment_request": PaymentRequestAgent(qbo_tools=self._qbo_tools),
            "vendor_onboarding": VendorOnboardingAgent(qbo_tools=self._qbo_tools),
            "sop_builder": SOPBuilderAgent(),
            "eod_report": EODReportAgent(),
            "controller": ControllerAgent(qbo_tools=self._qbo_tools),
            "bank_reconciliation": BankReconciliationAgent(qbo_tools=self._qbo_tools),
            "payroll_allocation": PayrollAllocationAgent(qbo_tools=self._qbo_tools),
        }

        self._graph = self._build_graph()

    def _build_graph(self) -> Any:
        graph = StateGraph(AgentState)

        # Add supervisor node
        graph.add_node("supervisor", self._supervisor_node)

        # Add one node per agent module
        for module_name in self._agents:
            graph.add_node(module_name, self._make_agent_node(module_name))

        # Routing edges
        graph.add_edge(START, "supervisor")
        graph.add_conditional_edges(
            "supervisor",
            self._route,
            {m: m for m in self._agents} | {"__end__": END},
        )

        # All agent nodes → END
        for module_name in self._agents:
            graph.add_edge(module_name, END)

        return graph.compile()

    async def _supervisor_node(self, state: AgentState) -> dict:
        """Classify intent and set active_module."""
        last_message = state["messages"][-1]
        content = last_message.content if isinstance(last_message.content, str) else ""

        messages = [
            SystemMessage(content=_ROUTER_SYSTEM),
            HumanMessage(content=content),
        ]

        response = await self._router_llm.ainvoke(messages)
        module = str(response.content).strip().lower()

        # Validate module
        if module not in self._agents:
            module = "controller"  # default fallback

        logger.info("Orchestrator routing", module=module, message_preview=content[:80])

        return {"active_module": module}

    def _route(self, state: AgentState) -> str:
        return state.get("active_module", "__end__")

    def _make_agent_node(self, module_name: str):
        """Factory: creates a LangGraph node function for a given agent."""
        agent = self._agents[module_name]

        async def agent_node(state: AgentState) -> dict:
            last_message = state["messages"][-1]
            content = last_message.content if isinstance(last_message.content, str) else ""

            # Build history from previous messages (excluding system messages)
            history = [
                m for m in state["messages"][:-1]
                if not isinstance(m, SystemMessage)
            ]

            result = await agent.run(
                user_input=content,
                history=history if history else None,
                context=state.get("context"),
            )

            return {
                "messages": [AIMessage(content=result["content"])],
                "tool_calls_made": result.get("tool_calls_made", []),
            }

        agent_node.__name__ = f"{module_name}_node"
        return agent_node

    async def invoke(
        self,
        user_message: str,
        conversation_id: str | None = None,
        qbo_realm_id: str | None = None,
        context: dict[str, Any] | None = None,
        history: list[BaseMessage] | None = None,
    ) -> dict[str, Any]:
        """Run the orchestrator and return the full response."""
        thread_id = conversation_id or str(uuid.uuid4())

        initial_state: AgentState = {
            "messages": [*(history or []), HumanMessage(content=user_message)],
            "active_module": "orchestrator",
            "qbo_realm_id": qbo_realm_id,
            "context": context or {},
            "tool_calls_made": [],
        }

        config = {"configurable": {"thread_id": thread_id}}
        result = await self._graph.ainvoke(initial_state, config)

        final_message = result["messages"][-1]
        content = (
            final_message.content
            if isinstance(final_message.content, str)
            else str(final_message.content)
        )

        return {
            "conversation_id": thread_id,
            "module": result.get("active_module", "unknown"),
            "content": content,
            "tool_calls_made": result.get("tool_calls_made", []),
        }

    async def stream(
        self,
        user_message: str,
        conversation_id: str | None = None,
        qbo_realm_id: str | None = None,
        context: dict[str, Any] | None = None,
    ):
        """
        Stream the response token-by-token.
        First classifies intent, then streams from the appropriate agent.
        """
        # Classify intent
        classification_messages = [
            SystemMessage(content=_ROUTER_SYSTEM),
            HumanMessage(content=user_message),
        ]
        clf_response = await self._router_llm.ainvoke(classification_messages)
        module = str(clf_response.content).strip().lower()
        if module not in self._agents:
            module = "controller"

        logger.info("Orchestrator stream routing", module=module)

        # Yield module info as first SSE event
        yield f"data: {{\"module\": \"{module}\", \"type\": \"routing\"}}\n\n"

        # Stream from specialist agent
        agent = self._agents[module]
        async for chunk in agent.stream(user_message, context=context):
            if chunk:
                # SSE format
                import json
                yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"

        yield 'data: {"type": "done"}\n\n'

    def update_qbo_tools(self, qbo_tools: list[BaseTool]) -> None:
        """Hot-swap QBO tools (e.g., after OAuth token refresh)."""
        self._qbo_tools = qbo_tools
        for agent in [
            "qbo_auditor", "grant_compliance", "payment_request",
            "vendor_onboarding", "controller", "bank_reconciliation",
            "payroll_allocation", "transaction_coder",
        ]:
            if agent in self._agents:
                self._agents[agent]._tools = (
                    self._agents[agent]._default_tools() + qbo_tools
                )
                self._agents[agent]._llm_with_tools = (
                    self._agents[agent]._llm.bind_tools(self._agents[agent]._tools)
                )
