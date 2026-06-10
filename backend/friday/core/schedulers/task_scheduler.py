import asyncio
from typing import Dict, List, Set, Any, Callable
from loguru import logger
from uuid import UUID, uuid4

class DAGNode:
    def __init__(self, node_id: str, execute_fn: Callable[[], Any], dependencies: List[str] = None):
        self.node_id: str = node_id
        self.execute_fn: Callable[[], Any] = execute_fn
        self.dependencies: List[str] = dependencies or []
        self.status: str = "PENDING"  # PENDING, RUNNING, SUCCESS, FAILED
        self.result: Any = None

class TaskDAGScheduler:
    def __init__(self):
        self.nodes: Dict[str, DAGNode] = {}
        self.plan_status: str = "SUCCESS"  # SUCCESS, PARTIAL_COMPLETE

    def add_node(self, node_id: str, execute_fn: Callable[[], Any], dependencies: List[str] = None) -> None:
        self.nodes[node_id] = DAGNode(node_id, execute_fn, dependencies)

    async def execute(self) -> Dict[str, Any]:
        logger.info(f"[TaskDAGScheduler] Starting DAG execution of {len(self.nodes)} nodes.")
        
        running_tasks = {}
        event = asyncio.Event()

        def task_done_callback(node_id, future):
            event.set()

        while True:
            all_done = all(node.status in ("SUCCESS", "FAILED") for node in self.nodes.values())
            if all_done:
                break

            ready_nodes = []
            for node_id, node in self.nodes.items():
                if node.status == "PENDING":
                    deps_ok = True
                    for dep_id in node.dependencies:
                        if dep_id not in self.nodes or self.nodes[dep_id].status != "SUCCESS":
                            deps_ok = False
                            break
                    if deps_ok:
                        ready_nodes.append(node)

            for node in ready_nodes:
                node.status = "RUNNING"
                task = asyncio.create_task(self._run_node_with_retry(node))
                running_tasks[node.node_id] = task
                task.add_done_callback(lambda f, n_id=node.node_id: task_done_callback(n_id, f))

            if not ready_nodes and not running_tasks:
                logger.warning("[TaskDAGScheduler] Deadlock or skipped nodes detected due to failed dependency parents.")
                for node in self.nodes.values():
                    if node.status == "PENDING":
                        node.status = "FAILED"
                        self.plan_status = "PARTIAL_COMPLETE"
                break

            event.clear()
            await event.wait()

            finished_ids = [n_id for n_id, t in running_tasks.items() if t.done()]
            for n_id in finished_ids:
                running_tasks.pop(n_id)

        results = {node_id: node.result for node_id, node in self.nodes.items()}
        logger.info(f"[TaskDAGScheduler] DAG execution complete. Plan Status: {self.plan_status}")
        return {
            "status": self.plan_status,
            "results": results
        }

    async def _run_node_with_retry(self, node: DAGNode) -> None:
        logger.info(f"[TaskDAGScheduler] Node {node.node_id} starting execution.")
        for attempt in range(2):
            try:
                if asyncio.iscoroutinefunction(node.execute_fn):
                    res = await node.execute_fn()
                else:
                    res = await asyncio.get_running_loop().run_in_executor(None, node.execute_fn)
                
                from friday.core.events import TaskResult, TaskStatus
                if isinstance(res, TaskResult) and res.status in (TaskStatus.FAILED, TaskStatus.TIMEOUT):
                    raise RuntimeError(f"TaskResult returned failure: {res.payload}")
                
                node.status = "SUCCESS"
                node.result = res
                logger.info(f"[TaskDAGScheduler] Node {node.node_id} completed successfully.")
                return
            except Exception as e:
                logger.warning(f"[TaskDAGScheduler] Node {node.node_id} failed on attempt {attempt + 1}: {e}")
                if attempt == 0:
                    await asyncio.sleep(0.2)
                else:
                    node.status = "FAILED"
                    node.result = str(e)
                    self.plan_status = "PARTIAL_COMPLETE"
                    logger.error(f"[TaskDAGScheduler] Node {node.node_id} failed permanently after 2 attempts.")

class TaskScheduler:
    def submit_dag(self, tasks: List[Any], correlation_id: UUID, session_id: UUID) -> None:
        """Submits a list of TaskDispatch objects to be executed as a DAG in the background."""
        logger.info(f"[TaskScheduler] Submitting DAG with {len(tasks)} tasks (correlation_id={correlation_id})")
        asyncio.create_task(self._execute_tasks_as_dag(tasks, correlation_id, session_id))

    async def _execute_tasks_as_dag(self, tasks: List[Any], correlation_id: UUID, session_id: UUID) -> None:
        from friday.core.events import EventEnvelope, EventPriority, TaskResult, TaskStatus
        from friday.core.event_bus import event_bus

        dag_scheduler = TaskDAGScheduler()

        async def run_task_node(task: Any) -> Any:
            future = asyncio.Future()

            async def on_result(env: EventEnvelope) -> None:
                payload = env.payload
                t_id = payload.get("task_id")
                if t_id and str(t_id) == str(task.task_id):
                    if not future.done():
                        future.set_result(payload)

            # Subscribe to all agent results
            event_bus.subscribe("friday.agent.*.result", on_result)

            try:
                # Convert UUID fields to string if necessary for serialization
                payload_dict = {
                    "task_id": str(task.task_id),
                    "session_id": str(task.session_id),
                    "agent_type": task.agent_type.value,
                    "intent": task.intent,
                    "parameters": task.parameters,
                    "timeout_ms": task.timeout_ms,
                    "priority": task.priority.value,
                    "requires_permission": [p.value for p in task.requires_permission],
                    "correlation_id": str(task.correlation_id)
                }

                dispatch_envelope = EventEnvelope(
                    topic=f"friday.agent.{task.agent_type.value.lower()}.dispatch",
                    priority=task.priority,
                    source="task_scheduler",
                    correlation_id=correlation_id,
                    session_id=session_id,
                    payload=payload_dict
                )
                await event_bus.publish(dispatch_envelope)

                timeout_sec = task.timeout_ms / 1000.0
                result_payload = await asyncio.wait_for(future, timeout=timeout_sec)
                return result_payload
            except Exception as e:
                logger.error(f"[TaskScheduler] Exception in node {task.task_id} ({task.intent}): {e}")
                return {
                    "task_id": str(task.task_id),
                    "status": "FAILED",
                    "payload": {"error": str(e)},
                    "correlation_id": str(correlation_id)
                }
            finally:
                event_bus.unsubscribe("friday.agent.*.result", on_result)

        # Build DAG (parallel execution defaults)
        for task in tasks:
            # Wrap the task runner in a lambda/partial so the current task is bound
            node_id = str(task.task_id)
            dag_scheduler.add_node(
                node_id=node_id,
                execute_fn=lambda t=task: run_task_node(t)
            )

        logger.info(f"[TaskScheduler] Executing task DAG in background (correlation_id={correlation_id})")
        await dag_scheduler.execute()

# Global singleton task scheduler
task_scheduler = TaskScheduler()

