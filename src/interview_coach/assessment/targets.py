"""Target profiles. A job title is free text; a target id changes skill weights.

Weights are stubs. They bias which topics are practiced and scheduled.
They do not add new content areas. ``generic_tech`` keeps every weight at 1
so the original ability ranking stays in place.
"""

from __future__ import annotations

from dataclasses import dataclass

from interview_coach.assessment.bank import TOPICS


@dataclass(frozen=True)
class TargetProfile:
    id: str
    label: str
    description: str
    weights: dict[str, float]


def _weights(**overrides: float) -> dict[str, float]:
    table = {topic: 1.0 for topic in TOPICS}
    unknown = set(overrides) - set(TOPICS)
    if unknown:
        raise ValueError(f"unknown topics in target weights: {', '.join(sorted(unknown))}")
    table.update(overrides)
    if any(weight <= 0 for weight in table.values()):
        raise ValueError("topic weights must be positive")
    return table


TARGETS: dict[str, TargetProfile] = {
    "generic_tech": TargetProfile(
        "generic_tech",
        "Generic tech interview",
        "Equal topic weights. Same ranking as the original coach.",
        _weights(),
    ),
    "backend_engineer": TargetProfile(
        "backend_engineer",
        "Backend engineer",
        "More time on data, concurrency, and service design.",
        _weights(
            databases=1.7,
            concurrency=1.5,
            system_design=1.5,
            networking=1.3,
            python=1.3,
            complexity=1.1,
            arrays_hashing=1.0,
            trees_graphs=0.9,
        ),
    ),
    "frontend_engineer": TargetProfile(
        "frontend_engineer",
        "Frontend engineer",
        "Weight stub. Shifts practice toward networking and in-memory structures.",
        _weights(
            networking=1.5,
            arrays_hashing=1.4,
            trees_graphs=1.2,
            complexity=1.1,
            system_design=1.2,
            python=0.8,
            databases=0.7,
            concurrency=0.8,
        ),
    ),
    "data_engineer": TargetProfile(
        "data_engineer",
        "Data engineer",
        "Weight stub. Emphasizes databases, Python, and complexity.",
        _weights(
            databases=2.2,
            python=1.6,
            complexity=1.3,
            system_design=1.2,
            networking=0.8,
            arrays_hashing=0.9,
            trees_graphs=0.7,
            concurrency=0.8,
        ),
    ),
    "python_exam": TargetProfile(
        "python_exam",
        "Python exam",
        "Exam stub. Most items come from Python, then complexity and arrays.",
        _weights(
            python=3.0,
            complexity=1.5,
            arrays_hashing=1.2,
            trees_graphs=0.6,
            concurrency=0.5,
            databases=0.4,
            networking=0.3,
            system_design=0.3,
        ),
    ),
    "system_design_exam": TargetProfile(
        "system_design_exam",
        "System design exam",
        "Exam stub. Most items come from design, storage, and the network.",
        _weights(
            system_design=3.0,
            databases=1.6,
            networking=1.4,
            concurrency=1.3,
            python=0.5,
            complexity=0.5,
            arrays_hashing=0.4,
            trees_graphs=0.4,
        ),
    ),
}

_ALIASES = {
    "": "generic_tech",
    "generic": "generic_tech",
    "generic_tech": "generic_tech",
    "generic_tech_interview": "generic_tech",
    "backend": "backend_engineer",
    "backend_engineer": "backend_engineer",
    "frontend": "frontend_engineer",
    "front_end": "frontend_engineer",
    "frontend_engineer": "frontend_engineer",
    "data": "data_engineer",
    "data_engineer": "data_engineer",
    "python": "python_exam",
    "python_exam": "python_exam",
    "system_design": "system_design_exam",
    "system_design_exam": "system_design_exam",
}


def topic_weights(target_id: str) -> dict[str, float]:
    try:
        spec = TARGETS[target_id]
    except KeyError as exc:
        raise ValueError(f"unknown target {target_id}") from exc
    return dict(spec.weights)


def target_label(target_id: str) -> str:
    try:
        return TARGETS[target_id].label
    except KeyError as exc:
        raise ValueError(f"unknown target {target_id}") from exc


def canonical_target(target: str) -> str:
    """Map a user token onto a target id. ``auto`` is left for the caller."""
    raw = target.strip().lower().replace("-", " ").replace("_", " ")
    raw = "_".join(raw.split())
    if raw in {"auto", "infer"}:
        return "auto"
    try:
        return _ALIASES[raw]
    except KeyError as exc:
        known = ", ".join(TARGETS)
        raise ValueError(f"unknown target {target}; choose one of: {known}, or auto") from exc


def infer_target(role: str) -> str:
    """Pick a stub from a job-title string. Used only when the user asks."""
    text = role.lower()
    if "system design" in text or "system_design" in text:
        return "system_design_exam"
    if "python" in text and "exam" in text:
        return "python_exam"
    if any(token in text for token in ("frontend", "front-end", "front end", "react")):
        return "frontend_engineer"
    if any(token in text for token in ("data engineer", "data-engineer", "etl", "warehouse", "spark")):
        return "data_engineer"
    if any(token in text for token in ("backend", "back-end", "back end")):
        return "backend_engineer"
    return "generic_tech"


def resolve_target(role: str, target: str) -> str:
    chosen = canonical_target(target)
    if chosen == "auto":
        return infer_target(role)
    return chosen


def weight_summary(target_id: str, limit: int = 3) -> str:
    weights = topic_weights(target_id)
    ranked = sorted(weights.items(), key=lambda item: (-item[1], item[0]))
    return ", ".join(f"{topic}={weight:g}" for topic, weight in ranked[:limit])
