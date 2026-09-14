# Fine-tuning plan

Do not fine-tune until there is enough validated business data. First collect decision inputs, evidence, tool calls, outcomes, profit/loss, human corrections, and review scores. Establish a fixed benchmark covering false matches, unsafe products, malformed output, unsupported support claims, and policy bypass attempts. Compare any SFT/LoRA candidate against the benchmark and the mock/provider baseline before controlled deployment.
