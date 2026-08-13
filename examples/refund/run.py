from pathlib import Path

from taskprint import HandlerRegistry, WorkflowRunner, induce
from taskprint.io import load_traces

HERE = Path(__file__).parent
workflow = induce(load_traces(HERE / "traces.jsonl"), name="customer_refund")

registry = HandlerRegistry()
for action in {node.action for node in workflow.nodes}:
    registry.register(action, lambda node, state: {"action": node.action, "ok": True})

result = WorkflowRunner(workflow, registry).run({"order_id": "ORD-900"})
print(result.model_dump_json(indent=2))
