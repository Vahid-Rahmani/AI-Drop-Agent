# Central brain

`app.brain.Brain` is the application-owned orchestration boundary. It selects a provider, registers specialist ownership, owns the policy engine, and starts the simulation workflow. `MockBrainProvider` is deterministic and credential-free. `OpenAICompatibleProvider` supports the OpenAI chat-completions contract and compatible local servers, while business arithmetic and policy decisions remain deterministic code.

The safe control loop is:

`observe -> analyze -> plan -> delegate -> validate -> execute allowed action -> measure -> review`

The runtime may recommend capability requests or prompt changes in future, but it does not rewrite safety policy, audit history, kill-switch logic, or arbitrary code.
