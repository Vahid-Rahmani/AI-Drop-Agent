# Local model boundary

`OpenAICompatibleProvider` accepts a configurable base URL and model name, so a future vLLM, llama.cpp server, Ollama-compatible gateway, or other compatible inference service can be used without changing business agents. Configure `LOCAL_MODEL_BASE_URL`, `LOCAL_MODEL_NAME`, and timeout values in deployment configuration.

Local inference does not remove the need for evidence grounding, structured output validation, policy enforcement, evaluation, redacted logs, and human review for high-impact actions.
