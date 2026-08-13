# Taskprint strategy

## Category

**Outcome-directed workflow induction infrastructure** — the layer that learns how work is
performed, removes accidental behavior, and selects the best feasible process before an agent
framework executes it.

## Where to play

- Developers building browser, operations, and back-office agents
- Repeated digital work with observable inputs, actions, decisions, and outcomes
- Tasks where successful demonstrations exist but formal specifications do not
- Python first; framework-neutral artifacts; export into existing runtimes

## Where not to play

- General-purpose agent orchestration
- RAG, document search, embeddings, or vector storage
- Model hosting or a unified LLM API
- No-code automation for nontechnical buyers in the first phase
- Broad compliance and agent-governance platforms

## How to win

1. **Own the artifact.** Make `.taskprint.json` the portable representation of learned work.
2. **Make value visible in five minutes.** Three included traces must produce a branch graph,
   held-out metrics, and a runnable workflow without an API key.
3. **Benchmark the missing step.** Publish WorkflowBench around induction quality, not model
   trivia or generic agent success.
4. **Integrate downstream.** Export to LangGraph, CrewAI, OpenAI Agents, and plain Python rather
   than competing with their runtimes.
5. **Monetize upstream difficulty.** Charge for multimodal capture and trace normalization,
   analogous to the open LlamaIndex ecosystem plus paid LlamaParse.
6. **Optimize outcomes, not clicks.** Own the portable Outcome Contract and the evidence loop that
   distinguishes a faithfully copied process from a safer, faster, more valuable one.

## Demand creation

The market does not yet commonly search for “workflow induction.” Demand must be created by
showing a painful before/after:

> We recorded five people processing the same task. Taskprint discovered the seven common
> steps, two branches, and one undocumented exception. Of three feasible designs, the selected
> workflow preserved a 98% success rate while cutting review time by 41% on held-out cases.

Every launch artifact should contain a downloadable trace dataset, the induced workflow, a
visual diff, held-out results, and runnable code. The result is the marketing.

## Distribution sequence

1. Recruit 10 design partners from Playwright/browser-agent and operations-automation
   communities; manually normalize their traces.
2. Turn the best three into public, reproducible case studies and seed WorkflowBench.
3. Release the trace spec, core library, and benchmark together—not an empty repository.
4. Build downstream exporters requested by real users to borrow distribution from established
   ecosystems.
5. Launch Capture only after normalization is the repeated bottleneck observed in core users.
6. Publish a monthly “State of Learned Workflows” report using aggregate benchmark results.

## Primary metric

**Useful optimized workflow rate:** percentage of unseen task families for which Taskprint
produces a constraint-safe workflow that reaches agreed held-out outcome and coverage thresholds
with fewer than five human edits.

GitHub stars, downloads, and generated workflows are supporting metrics. They are not proof
that the category works.
