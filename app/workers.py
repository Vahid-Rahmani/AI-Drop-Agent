"""Small API-independent job runner for scheduled sync and review work."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


class JobNotFoundError(KeyError):
    """Raised when a worker is asked to run an unregistered job."""


@dataclass(frozen=True)
class Job:
    name: str
    handler: Callable[[dict[str, Any]], dict[str, Any]]
    max_attempts: int = 1


class Worker:
    """Deterministic one-shot runner; process supervision belongs to deployment."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def register(self, job: Job) -> None:
        if job.name in self._jobs:
            raise ValueError(f"job already registered: {job.name}")
        if job.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self._jobs[job.name] = job

    def run_once(self, name: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            job = self._jobs[name]
        except KeyError as error:
            raise JobNotFoundError(name) from error
        last_error: Exception | None = None
        for _ in range(job.max_attempts):
            try:
                return job.handler(payload or {})
            except Exception as error:
                last_error = error
        raise RuntimeError(f"job failed after {job.max_attempts} attempts: {name}") from last_error

    def list(self) -> list[Job]:
        return list(self._jobs.values())

