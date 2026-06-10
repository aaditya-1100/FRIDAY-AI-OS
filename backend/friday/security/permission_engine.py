import asyncio
from typing import Dict, Any, Optional
from loguru import logger
from uuid import uuid4, UUID
from friday.core.events import AgentType, AgentTrustLevel, PermissionEnum, EventEnvelope, EventPriority
from friday.core.event_bus import event_bus
from friday.security.capability_registry import AGENT_TRUST_MAP, TOOL_PERMISSION_MAP, TRUST_LIMIT_MAP
from friday.security.audit_log import audit_logger

PERMISSION_VALUES = {
    PermissionEnum.READ_ONLY: 0,
    PermissionEnum.WRITE_SAFE: 1,
    PermissionEnum.ELEVATED: 2,
    PermissionEnum.PRIVILEGED: 3,
    PermissionEnum.HUMAN_CONFIRMED: 4
}

class PermissionEngine:
    def __init__(self):
        self._pending_confirmations: Dict[str, asyncio.Future] = {}
        event_bus.subscribe("friday.tool.user_confirmed", self._on_user_confirmed)

    async def _on_user_confirmed(self, envelope: EventEnvelope):
        corr_id = str(envelope.correlation_id)
        if corr_id in self._pending_confirmations:
            future = self._pending_confirmations[corr_id]
            if not future.done():
                future.set_result(True)

    async def authorize_and_check(
        self,
        agent_id: UUID,
        agent_type: AgentType,
        tool_name: str,
        correlation_id: UUID,
        session_id: UUID
    ) -> bool:
        trust_level = AGENT_TRUST_MAP.get(agent_type, AgentTrustLevel.STANDARD)
        max_allowed = TRUST_LIMIT_MAP.get(trust_level, PermissionEnum.READ_ONLY)
        required = TOOL_PERMISSION_MAP.get(tool_name, PermissionEnum.ELEVATED)
        
        allowed_val = PERMISSION_VALUES[max_allowed]
        required_val = PERMISSION_VALUES[required]
        
        corr_str = str(correlation_id)
        
        if allowed_val < required_val:
            if required in (PermissionEnum.PRIVILEGED, PermissionEnum.HUMAN_CONFIRMED) and trust_level != AgentTrustLevel.SANDBOXED:
                pass
            else:
                reason = f"Agent trust level {trust_level.value} (limit={max_allowed.value}) is insufficient for tool {tool_name} (requires={required.value})."
                audit_logger.log_tool_call(
                    agent_id=str(agent_id),
                    tool_name=tool_name,
                    permission_level=required.value,
                    granted=False,
                    reason=reason,
                    correlation_id=corr_str
                )
                return False


        if required in (PermissionEnum.PRIVILEGED, PermissionEnum.HUMAN_CONFIRMED):
            logger.info(f"[PermissionEngine] Tool {tool_name} requires human confirmation. Initiating flow.")
            
            confirm_envelope = EventEnvelope(
                topic="friday.tool.confirm_required",
                priority=EventPriority.P0,
                source="security.permission_engine",
                correlation_id=correlation_id,
                session_id=session_id,
                payload={
                    "agent_id": str(agent_id),
                    "tool_name": tool_name,
                    "reason": f"Execution of {tool_name} requires confirmation"
                }
            )
            await event_bus.publish(confirm_envelope)
            
            future = asyncio.get_running_loop().create_future()
            self._pending_confirmations[corr_str] = future
            
            try:
                await asyncio.wait_for(future, timeout=30.0)
                audit_logger.log_tool_call(
                    agent_id=str(agent_id),
                    tool_name=tool_name,
                    permission_level=required.value,
                    granted=True,
                    reason="User confirmed via interface",
                    correlation_id=corr_str
                )
                return True
            except asyncio.TimeoutError:
                logger.warning(f"[PermissionEngine] Confirmation timed out for tool {tool_name}.")
                timeout_envelope = EventEnvelope(
                    topic="friday.tool.confirm_timeout",
                    priority=EventPriority.P0,
                    source="security.permission_engine",
                    correlation_id=correlation_id,
                    session_id=session_id,
                    payload={
                        "agent_id": str(agent_id),
                        "tool_name": tool_name,
                        "reason": "Confirmation timed out after 30 seconds"
                    }
                )
                await event_bus.publish(timeout_envelope)
                
                audit_logger.log_tool_call(
                    agent_id=str(agent_id),
                    tool_name=tool_name,
                    permission_level=required.value,
                    granted=False,
                    reason="Confirmation timed out after 30 seconds",
                    correlation_id=corr_str
                )
                return False
            finally:
                self._pending_confirmations.pop(corr_str, None)

        audit_logger.log_tool_call(
            agent_id=str(agent_id),
            tool_name=tool_name,
            permission_level=required.value,
            granted=True,
            reason="Authorized by capability registry policy mapping",
            correlation_id=corr_str
        )
        return True

    async def check_permission(
        self,
        agent_trust_level: AgentTrustLevel,
        tool_name: str,
        agent_id: Optional[UUID] = None,
        correlation_id: Optional[UUID] = None,
        session_id: Optional[UUID] = None
    ) -> bool:
        max_allowed = TRUST_LIMIT_MAP.get(agent_trust_level, PermissionEnum.READ_ONLY)
        required = TOOL_PERMISSION_MAP.get(tool_name, PermissionEnum.ELEVATED)
        
        allowed_val = PERMISSION_VALUES[max_allowed]
        required_val = PERMISSION_VALUES[required]
        
        corr_id = correlation_id or uuid4()
        sess_id = session_id or uuid4()
        a_id = agent_id or uuid4()
        corr_str = str(corr_id)
        
        if allowed_val < required_val:
            if required in (PermissionEnum.PRIVILEGED, PermissionEnum.HUMAN_CONFIRMED) and agent_trust_level != AgentTrustLevel.SANDBOXED:
                pass
            else:
                reason = f"Agent trust level {agent_trust_level.value} (limit={max_allowed.value}) is insufficient for tool {tool_name} (requires={required.value})."
                audit_logger.log_tool_call(
                    agent_id=str(a_id),
                    tool_name=tool_name,
                    permission_level=required.value,
                    granted=False,
                    reason=reason,
                    correlation_id=corr_str
                )
                return False

        if required in (PermissionEnum.PRIVILEGED, PermissionEnum.HUMAN_CONFIRMED):
            logger.info(f"[PermissionEngine] Tool {tool_name} requires human confirmation. Initiating flow.")
            confirm_envelope = EventEnvelope(
                topic="friday.tool.confirm_required",
                priority=EventPriority.P0,
                source="security.permission_engine",
                correlation_id=corr_id,
                session_id=sess_id,
                payload={
                    "agent_id": str(a_id),
                    "tool_name": tool_name,
                    "reason": f"Execution of {tool_name} requires confirmation"
                }
            )
            await event_bus.publish(confirm_envelope)
            
            future = asyncio.get_running_loop().create_future()
            self._pending_confirmations[corr_str] = future
            
            try:
                await asyncio.wait_for(future, timeout=30.0)
                audit_logger.log_tool_call(
                    agent_id=str(a_id),
                    tool_name=tool_name,
                    permission_level=required.value,
                    granted=True,
                    reason="User confirmed via interface",
                    correlation_id=corr_str
                )
                return True
            except asyncio.TimeoutError:
                logger.warning(f"[PermissionEngine] Confirmation timed out for tool {tool_name}.")
                timeout_envelope = EventEnvelope(
                    topic="friday.tool.confirm_timeout",
                    priority=EventPriority.P0,
                    source="security.permission_engine",
                    correlation_id=corr_id,
                    session_id=sess_id,
                    payload={
                        "agent_id": str(a_id),
                        "tool_name": tool_name,
                        "reason": "Confirmation timed out after 30 seconds"
                    }
                )
                await event_bus.publish(timeout_envelope)
                audit_logger.log_tool_call(
                    agent_id=str(a_id),
                    tool_name=tool_name,
                    permission_level=required.value,
                    granted=False,
                    reason="Confirmation timed out after 30 seconds",
                    correlation_id=corr_str
                )
                return False
            finally:
                self._pending_confirmations.pop(corr_str, None)

        audit_logger.log_tool_call(
            agent_id=str(a_id),
            tool_name=tool_name,
            permission_level=required.value,
            granted=True,
            reason="Authorized by capability registry policy mapping",
            correlation_id=corr_str
        )
        return True

permission_engine = PermissionEngine()
