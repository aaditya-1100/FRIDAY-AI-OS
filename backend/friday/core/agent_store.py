"""
agent_store.py — Global agent instance store for dispatcher access.
Populated by main.py after agents are started. Thread-safe dict.
"""
from friday.core.events import AgentType

# Dict[AgentType, BaseAgent] — populated at startup
_agents: dict = {}


def register(agent) -> None:
    """Called by main.py after each agent.start()."""
    _agents[agent.agent_type] = agent


def get(agent_type: AgentType):
    """Return running agent instance for the given type, or None."""
    return _agents.get(agent_type)


def all_agents() -> dict:
    return dict(_agents)
