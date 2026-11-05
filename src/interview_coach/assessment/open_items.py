"""One open prompt per topic. Scored locally by rubric keywords."""

from __future__ import annotations

from interview_coach.models import Question, RubricPoint


def _open(
    qid: str,
    topic: str,
    difficulty: int,
    prompt: str,
    explanation: str,
    tags: tuple[str, ...],
    points: tuple[RubricPoint, ...],
) -> Question:
    return Question(
        id=qid,
        topic=topic,
        difficulty=difficulty,
        prompt=prompt,
        choices=(),
        answer=-1,
        explanation=explanation,
        kind="open",
        tags=tags,
        rubric=points,
    )


def _point(label: str, *keywords: str) -> RubricPoint:
    return RubricPoint(label, keywords)


OPEN_QUESTIONS: tuple[Question, ...] = (
    _open(
        "ah-open",
        "arrays_hashing",
        3,
        "Explain how a dynamic hash map keeps expected lookups cheap as it grows.",
        "A bounded load factor, a collision strategy, and geometric resizing keep the expected cost flat.",
        ("hashing", "amortized"),
        (
            _point("Mentions the load factor or bucket fullness", "load factor", "fullness"),
            _point("Describes a collision strategy", "chaining", "probing", "collision"),
            _point("Explains why resizing is cheap across many inserts", "amortized", "doubling", "resize"),
        ),
    ),
    _open(
        "tg-open",
        "trees_graphs",
        4,
        "When would you choose Dijkstra instead of plain breadth-first search?",
        "Dijkstra is for weighted shortest paths when every edge weight is non-negative. BFS is for unweighted hops.",
        ("graphs", "shortest-path"),
        (
            _point("Names a weighted graph or weighted edges", "weighted"),
            _point("Requires non-negative weights", "non-negative", "nonnegative", "no negative"),
            _point("States the goal is a shortest path", "shortest path", "shortest-path"),
        ),
    ),
    _open(
        "cx-open",
        "complexity",
        2,
        "Why is binary search logarithmic rather than linear?",
        "The array must be sorted. Each comparison discards half of the remaining range, so the depth is log n.",
        ("search", "logarithms"),
        (
            _point("Requires the input to be sorted", "sorted"),
            _point("Says each step discards half the range", "half", "halves"),
            _point("Names the logarithmic bound", "log", "logarithmic"),
        ),
    ),
    _open(
        "db-open",
        "databases",
        4,
        "What problem does MVCC solve for readers and writers?",
        "MVCC keeps versions so a reader can use a snapshot while a writer creates a new version, instead of blocking.",
        ("transactions", "mvcc"),
        (
            _point("Mentions a snapshot or a consistent view", "snapshot"),
            _point("Says readers need not block writers", "do not block", "don't block", "without blocking", "does not block"),
            _point("Mentions row versions or multiple versions", "version"),
        ),
    ),
    _open(
        "net-open",
        "networking",
        3,
        "What does the TCP three-way handshake establish before data is sent?",
        "SYN, SYN-ACK, and ACK open a reliable connection and exchange the starting sequence numbers.",
        ("tcp",),
        (
            _point("Names the SYN / SYN-ACK / ACK exchange", "syn"),
            _point("Says a connection is established", "connection"),
            _point("Mentions sequence numbers or acknowledgements", "sequence", "acknowledg"),
        ),
    ),
    _open(
        "py-open",
        "python",
        4,
        "Why is a mutable default argument, such as `def f(items=[])`, a bug?",
        "Default objects are created once, when the function is defined, and then shared by later calls that omit the argument.",
        ("functions", "mutability"),
        (
            _point("Says the default is created once", "once", "definition time", "defined once"),
            _point("Says later calls share that object", "shared", "reused", "same list"),
            _point("Names the mutable object", "mutable", "list"),
        ),
    ),
    _open(
        "sd-open",
        "system_design",
        5,
        "What does an idempotency key protect when a client retries a write?",
        "The server remembers the key and the result, so a retry does not apply the side effect a second time.",
        ("reliability", "idempotency"),
        (
            _point("Mentions a retry", "retry", "retries"),
            _point("Prevents a duplicate side effect", "duplicate", "twice", "second time"),
            _point("Names the side effect or the stored result", "side effect", "result"),
        ),
    ),
    _open(
        "cc-open",
        "concurrency",
        3,
        "Name one Coffman condition for deadlock and why it matters.",
        "Circular wait, mutual exclusion, hold-and-wait, and no preemption are the classic conditions. Breaking one of them prevents deadlock.",
        ("deadlock", "locks"),
        (
            _point("Names deadlock or a Coffman condition", "deadlock", "circular wait", "hold-and-wait", "hold and wait"),
            _point("Mentions mutual exclusion or a lock", "mutual exclusion", "mutex", "lock"),
            _point("Says the condition is part of how deadlock forms", "condition", "prevent", "avoid"),
        ),
    ),
)


def open_question_for(topic: str) -> Question | None:
    for question in OPEN_QUESTIONS:
        if question.topic == topic:
            return question
    return None
