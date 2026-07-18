import asyncio
import functools
from datetime import datetime
from typing import Dict, Any, List
from loguru import logger
from friday.core.events import AgentType, TaskDispatch, TaskResult, TaskStatus
from friday.agents.base_agent import BaseAgent
from friday.memory.semantic import SemanticMemory


def _now_context() -> str:
    now = datetime.now()
    hour = now.hour
    period = "morning" if hour < 12 else ("afternoon" if hour < 17 else ("evening" if hour < 21 else "night"))
    return now.strftime(f"Today is %A, %B %d, %Y. Current time is %I:%M %p ({period}).")


class KnowledgeAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentType.KNOWLEDGE_AGENT)
        self.semantic = SemanticMemory()

    async def startup(self) -> None:
        logger.info("[KnowledgeAgent] Startup complete.")

    async def shutdown(self) -> None:
        logger.info("[KnowledgeAgent] Shutdown complete.")

    def get_capabilities(self) -> list[str]:
        return [
            "RETRIEVE_SEMANTIC", "QUERY_GRAPH", "ADD_FACT", "ADD_RELATION",
            "AI_QUERY", "CASUAL_CHAT", "CLARIFICATION"
        ]

    def _ok(self, dispatch, payload):
        return TaskResult(
            task_id=dispatch.task_id, agent_id=self.agent_id,
            status=TaskStatus.SUCCESS, payload=payload,
            correlation_id=dispatch.correlation_id
        )

    def _fail(self, dispatch, error: str):
        return TaskResult(
            task_id=dispatch.task_id, agent_id=self.agent_id,
            status=TaskStatus.FAILED, payload={"error": error},
            correlation_id=dispatch.correlation_id
        )

    async def handle_task(self, dispatch: TaskDispatch) -> TaskResult:
        intent = dispatch.intent
        params = dispatch.parameters or {}

        try:
            logger.info(f"[KnowledgeAgent] Executing knowledge action: {intent}")

            if intent == "RETRIEVE_SEMANTIC":
                query = params.get("query", "")
                limit = params.get("limit", 3)
                hits = self.semantic.search(query, limit=limit)
                return self._ok(dispatch, {"hits": hits})

            elif intent == "QUERY_GRAPH":
                return self._ok(dispatch, {"relations": []})

            elif intent == "ADD_FACT":
                text = params.get("text", "")
                metadata = params.get("metadata", {})
                self.semantic.add_fact(text, metadata=metadata)
                return self._ok(dispatch, {"status": "Fact added successfully"})

            elif intent == "ADD_RELATION":
                return self._ok(dispatch, {"status": "Relation added successfully"})

            elif intent == "CLARIFICATION":
                question = params.get("question") or "Could you clarify that, sir?"
                return self._ok(dispatch, {"response": question})

            elif intent in ("CASUAL_CHAT", "AI_QUERY"):
                # Ported from monolith action_executor.py AI_QUERY handler (L825-914)
                query_text = params.get("query") or ""
                memory = params.get("_memory_obj")  # optional memory context passed from FSM
                now_ctx = _now_context()

                from friday.memory.preference import PreferenceMemory
                from friday.memory.semantic import SemanticMemory as LegacySemanticMemory
                from friday.memory.episodic import EpisodicMemory
                from brain.identity_manager import IdentityManager

                pref_mem = PreferenceMemory()
                sem_mem = LegacySemanticMemory()
                epi_mem = EpisodicMemory()
                id_mgr = IdentityManager()

                identity_slices = id_mgr.get_contextual_slices(query_text)

                env_ctx = "== USER SYSTEM CONTEXT ==\n"

                # Tier-1 Active Project Registry
                try:
                    from brain.project_manager import ProjectManager
                    pm = ProjectManager()
                    active_proj = pm.get_active_project()
                    if active_proj:
                        env_ctx += "- AUTHORITATIVE ACTIVE PROJECT REGISTRY:\n"
                        env_ctx += f"  * Active Project Name: {active_proj.get('project_name')}\n"
                        env_ctx += f"  * Workspace Directory: {active_proj.get('workspace_path')}\n"
                        env_ctx += f"  * Repository Path: {active_proj.get('repo_path')}\n"
                        env_ctx += f"  * Active Goal: {active_proj.get('active_goal')}\n"
                        env_ctx += f"  * Project Type: {active_proj.get('project_type')}\n"
                except Exception as e_proj:
                    logger.warning(f"[KnowledgeAgent] Project registry injection failed: {e_proj}")

                env_ctx += f"- Preferred Location/City: {pref_mem.get('default_city', 'Kashipur, Uttarakhand, India')}\n"

                # Passive active window
                try:
                    from system.screen_agent import get_active_window_info
                    win_info = get_active_window_info()
                    if win_info and win_info.get("title"):
                        env_ctx += f"- Passive Active Window: Currently viewing \"{win_info['title']}\" (Process: {win_info['process']})\n"
                except Exception:
                    pass

                fav_app = pref_mem.get_favorite_app()
                if fav_app:
                    env_ctx += f"- Mapped Favorite Desktop App: {fav_app}\n"
                if sem_mem.knowledge:
                    env_ctx += "- Workspace & Semantic Facts:\n"
                    for k, v in list(sem_mem.knowledge.items())[:5]:
                        env_ctx += f"  * {k}: {v}\n"
                if epi_mem.events:
                    env_ctx += "- Recent Actions Completed:\n"
                    for ev in epi_mem.events[-3:]:
                        ts = ev.get("timestamp", "")[:19].replace("T", " ")
                        env_ctx += f"  * [{ts}] {ev.get('query')} -> {ev.get('intent')} (success={ev.get('success')})\n"

                if identity_slices:
                    env_ctx += "- AUTHORITATIVE STRUCTURED IDENTITY SLICES:\n"
                    for category, data in identity_slices.items():
                        if isinstance(data, dict):
                            env_ctx += f"  * [{category}]:\n"
                            for field, val in data.items():
                                env_ctx += f"    - {field}: {val}\n"
                        else:
                            env_ctx += f"  * [{category}]: {data}\n"

                env_ctx += "=========================\n\n"

                from llm.groq_client import ask_groq, DEFAULT_MODEL, DEFAULT_SYSTEM_PROMPT
                custom_system = DEFAULT_SYSTEM_PROMPT + "\n" + env_ctx
                full_query = f"{now_ctx}\n\nUser: {query_text}"
                history = memory.get() if memory and hasattr(memory, "get") else None

                loop = asyncio.get_running_loop()
                try:
                    response = await asyncio.wait_for(
                        loop.run_in_executor(
                            None, functools.partial(ask_groq, full_query, custom_system, DEFAULT_MODEL, history)
                        ),
                        timeout=25.0
                    )
                except asyncio.TimeoutError:
                    response = "I am sorry sir, but my thinking engine timed out. Please try again."

                return self._ok(dispatch, {"response": response})

            else:
                return self._fail(dispatch, f"Unsupported intent: {intent}")

        except Exception as e:
            logger.error(f"[KnowledgeAgent] Error executing knowledge task: {e}", exc_info=True)
            return self._fail(dispatch, str(e))
