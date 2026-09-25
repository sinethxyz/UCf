# Historical Architecture Note

The current runtime and architecture specification were written for Unicorn Foundry, the original implementation of UCF. They intentionally retain the original terminology.

## Generalized boundary

Environment -> Evidence + State(t) -> Intelligence -> Controlled Transition -> Outcome + Evidence -> State(t+1) -> repeat.

## Mapping from Foundry

| Historical Foundry concept | General UCF concept |
| --- | --- |
| TaskRequest | requested transition / intent |
| RunState | execution-state machine |
| PlanArtifact | proposed transition plan |
| Git worktree | isolated action environment |
| implementer agent | action executor |
| verification runner | deterministic transition validator |
| blind reviewer | independent evaluator |
| RunEvent | transition event |
| RunArtifact | durable evidence |
| PR | accepted/publishable action outcome |
| Claude provider | intelligence provider |
| Unicorn canon | environment/state contracts |

This mapping is interpretive. It describes the direction of the reopened project; it does not claim the historical runtime already provides a domain-independent implementation.

## Migration principle

Generalization should proceed from the outside inward:

1. establish the UCF thesis and vocabulary;
2. preserve the historical implementation;
3. identify Unicorn-specific assumptions;
4. introduce provider/environment interfaces where evidence justifies them;
5. migrate one closed-loop example end to end;
6. evaluate continuity, transition correctness, recovery, and state accuracy;
7. remove historical coupling only when replacement abstractions are exercised.

The goal is not abstraction for its own sake. The goal is to discover which mechanisms are genuinely necessary for coherent machine operation through time.
