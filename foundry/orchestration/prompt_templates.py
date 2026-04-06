"""System prompt templates for each subagent and task type.

Templates are loaded from .claude/agents/*.md files at runtime.
"""

from pathlib import Path

AGENTS_DIR = Path(__file__).resolve().parent.parent.parent / ".claude" / "agents"


def load_agent_prompt(agent_name: str) -> str:
    """Load a subagent's system prompt from its markdown definition.

    Args:
        agent_name: Name of the agent (e.g., 'planner', 'reviewer').

    Returns:
        The full text of the agent's system prompt.

    Raises:
        FileNotFoundError: If the agent definition file does not exist.
    """
    path = AGENTS_DIR / f"{agent_name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Agent definition not found: {path}")
    return path.read_text()
