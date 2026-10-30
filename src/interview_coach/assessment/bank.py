"""Local interview question bank."""

from __future__ import annotations

from interview_coach.models import Question

TOPICS: dict[str, str] = {
    "arrays_hashing": "Arrays & Hashing",
    "trees_graphs": "Trees & Graphs",
    "complexity": "Complexity",
    "databases": "Databases",
    "networking": "Networking",
    "python": "Python",
    "system_design": "System Design",
    "concurrency": "Concurrency",
}


def subject_label(topic: str) -> str:
    """Topic names without a Review/Mock prefix."""
    if topic.startswith(("review:", "mock:")):
        _, _, rest = topic.partition(":")
        return ", ".join(subject_label(part) for part in rest.split("+") if part)
    return TOPICS.get(topic, topic)


def display_topic(topic: str) -> str:
    if topic.startswith("review:"):
        return f"Review: {subject_label(topic)}"
    if topic.startswith("mock:"):
        return f"Mock: {subject_label(topic)}"
    return subject_label(topic)


def _q(
    qid: str,
    topic: str,
    difficulty: int,
    prompt: str,
    choices: tuple[str, str, str, str],
    answer: int,
    explanation: str,
) -> Question:
    return Question(qid, topic, difficulty, prompt, choices, answer, explanation)


QUESTIONS: tuple[Question, ...] = (
    _q(
        "ah-1",
        "arrays_hashing",
        1,
        "Average-case lookup in a hash map is:",
        ("O(1)", "O(log n)", "O(n)", "O(n log n)"),
        0,
        "With a decent hash and a bounded load factor, expected lookup is constant time.",
    ),
    _q(
        "ah-2",
        "arrays_hashing",
        2,
        "The usual one-pass solution for Two Sum stores:",
        (
            "A heap of the values",
            "Value to index in a hash map",
            "A sorted copy only",
            "Every pair in a matrix",
        ),
        1,
        "Record each seen value's index and probe for the complement.",
    ),
    _q(
        "ah-3",
        "arrays_hashing",
        3,
        "Separate chaining resolves collisions by:",
        (
            "Probing the next empty slot only",
            "Storing a collection of entries at each bucket",
            "Deleting both keys",
            "Requiring all keys to be integers",
        ),
        1,
        "Each bucket holds a chain (list or tree) of entries that hash there.",
    ),
    _q(
        "ah-4",
        "arrays_hashing",
        4,
        "A hash map lookup degrades toward O(n) when:",
        (
            "The table is empty",
            "Keys are strings",
            "Almost every key lands in one bucket",
            "You iterate the keys on purpose",
        ),
        2,
        "Pathological collisions or a broken hash turn the structure into one long chain.",
    ),
    _q(
        "ah-5",
        "arrays_hashing",
        5,
        "Inserting into a dynamic table that doubles when full is:",
        (
            "O(1) amortized",
            "O(log n) worst case every insert",
            "O(n) amortized",
            "O(n^2) amortized",
        ),
        0,
        "Geometric growth makes the occasional full copy cheap across many inserts.",
    ),
    _q(
        "tg-1",
        "trees_graphs",
        1,
        "In-order traversal of a binary search tree yields:",
        ("Reverse level order", "Keys in sorted order", "A random order", "Only the leaves"),
        1,
        "Left, node, right visits BST keys from smallest to largest.",
    ),
    _q(
        "tg-2",
        "trees_graphs",
        2,
        "Breadth-first search keeps frontier nodes in a:",
        ("Stack", "Queue", "Heap of node ids", "Union-find"),
        1,
        "A queue expands vertices in the order they were discovered.",
    ),
    _q(
        "tg-3",
        "trees_graphs",
        3,
        "A directed cycle can be detected by:",
        (
            "DFS with colors / a recursion stack",
            "Sorting the adjacency matrix",
            "Counting the edges only",
            "Running binary search",
        ),
        0,
        "A back edge into the current recursion stack means a directed cycle. Kahn's algorithm also works.",
    ),
    _q(
        "tg-4",
        "trees_graphs",
        4,
        "Classic Dijkstra requires:",
        (
            "Non-negative edge weights",
            "Negative cycles to be present",
            "An undirected graph",
            "Integer weights only",
        ),
        0,
        "Negative edges can make the greedy settle step wrong. Use Bellman-Ford then.",
    ),
    _q(
        "tg-5",
        "trees_graphs",
        5,
        "Union-find with path compression and union by rank has an amortized find cost bounded by:",
        (
            "O(n)",
            "The inverse Ackermann function (effectively constant)",
            "Exactly O(1) in the worst case",
            "O(n log n)",
        ),
        1,
        "The inverse Ackermann bound is not a strict O(1) worst case, but it is constant for practical n.",
    ),
    _q(
        "cx-1",
        "complexity",
        1,
        "Binary search on a sorted array is:",
        ("O(1)", "O(log n)", "O(n)", "O(n log n)"),
        1,
        "Each comparison discards half of the remaining range.",
    ),
    _q(
        "cx-2",
        "complexity",
        2,
        "Two nested loops that each run n times are:",
        ("O(n)", "O(n log n)", "O(n^2)", "O(2^n)"),
        2,
        "The inner loop repeats n times for each of n outer iterations.",
    ),
    _q(
        "cx-3",
        "complexity",
        3,
        "Mergesort's worst-case time is:",
        ("O(n)", "O(n log n)", "O(n^2)", "O(log n)"),
        1,
        "Every level does O(n) merging work and there are O(log n) levels.",
    ),
    _q(
        "cx-4",
        "complexity",
        4,
        "The recurrence T(n) = 2T(n/2) + O(n) solves to:",
        ("O(log n)", "O(n)", "O(n log n)", "O(n^2)"),
        2,
        "Master theorem case 2: the work per level matches the leaf cost, adding a log factor.",
    ),
    _q(
        "cx-5",
        "complexity",
        5,
        "n appends to a geometric dynamic array cost:",
        ("O(n) total", "O(n^2) total", "O(log n) total", "O(1) total"),
        0,
        "Each element is copied a constant number of times, so the whole sequence is linear.",
    ),
    _q(
        "db-1",
        "databases",
        1,
        "A primary key:",
        (
            "Uniquely identifies each row",
            "Must be a string",
            "Is optional on every row including duplicates",
            "Replaces the need for a table",
        ),
        0,
        "Primary-key values are unique and not null, so each row has one identity.",
    ),
    _q(
        "db-2",
        "databases",
        2,
        "A B-tree index most directly speeds up:",
        (
            "Equality and range lookups",
            "Full table rewrites only",
            "Network round trips",
            "CPU scheduling",
        ),
        0,
        "The ordered tree supports point lookups and ranges without scanning every row.",
    ),
    _q(
        "db-3",
        "databases",
        3,
        "A dirty read is reading:",
        (
            "Data changed by another transaction that has not committed",
            "Only your own uncommitted write, which is always forbidden",
            "A committed snapshot",
            "An index header",
        ),
        0,
        "Dirty reads observe uncommitted work that might still roll back.",
    ),
    _q(
        "db-4",
        "databases",
        4,
        "A covering index lets the engine:",
        (
            "Answer the query from the index without visiting the table",
            "Skip the transaction log",
            "Remove the primary key",
            "Avoid taking any locks",
        ),
        0,
        "If every selected and filtered column is in the index, the heap or table lookup is unnecessary.",
    ),
    _q(
        "db-5",
        "databases",
        5,
        "Under MVCC, a reader typically:",
        (
            "Sees a snapshot and does not block writers",
            "Locks every row in the database",
            "Always reads uncommitted writes",
            "Disables indexes",
        ),
        0,
        "Multiple versions let readers use a snapshot while writers create new versions.",
    ),
    _q(
        "net-1",
        "networking",
        1,
        "DNS primarily maps:",
        ("A hostname to an IP address", "IP to a MAC always", "SQL to a plan", "JSON to protobuf"),
        0,
        "The domain name system resolves names to addresses (and a few other record types).",
    ),
    _q(
        "net-2",
        "networking",
        2,
        "HTTP and TCP sit at which layers in the usual stack?",
        (
            "HTTP application, TCP transport",
            "Both are physical",
            "TCP application, HTTP transport",
            "Both are network-layer routing protocols",
        ),
        0,
        "HTTP is an application protocol. TCP provides the byte stream underneath.",
    ),
    _q(
        "net-3",
        "networking",
        3,
        "The TCP three-way handshake is:",
        ("SYN, SYN-ACK, ACK", "GET, POST, PUT", "SYN, FIN, RST", "ACK, ACK, ACK"),
        0,
        "SYN opens, SYN-ACK acknowledges and opens the other direction, ACK completes.",
    ),
    _q(
        "net-4",
        "networking",
        4,
        "TLS does not itself provide:",
        (
            "Authorization of a business action inside the app",
            "Confidentiality of the session bytes",
            "Integrity of the session bytes",
            "Server authentication via certificates",
        ),
        0,
        "TLS protects the transport. Application authorization is a separate decision.",
    ),
    _q(
        "net-5",
        "networking",
        5,
        "HTTP/3 reduces TCP head-of-line blocking by running over:",
        ("QUIC", "FTP", "SMTP", "ICMP only"),
        0,
        "QUIC multiplexes independent streams over UDP so one lost packet does not stall every stream.",
    ),
    _q(
        "py-1",
        "python",
        1,
        "A tuple differs from a list because a tuple is:",
        ("Immutable", "Always slower", "Limited to integers", "A hash table"),
        0,
        "Tuples cannot be resized or have items assigned. Lists can.",
    ),
    _q(
        "py-2",
        "python",
        2,
        "The CPython GIL means:",
        (
            "One thread runs Python bytecode at a time",
            "Processes cannot be spawned",
            "All IO is forbidden",
            "Lists are immutable",
        ),
        0,
        "The global interpreter lock serializes bytecode. IO and many C extensions release it.",
    ),
    _q(
        "py-3",
        "python",
        3,
        "`is` compared with `==` checks:",
        ("Identity versus equality", "Types versus lengths", "Hashes versus ids only", "Time versus memory"),
        0,
        "`is` is object identity. `==` calls equality and can be true for distinct objects.",
    ),
    _q(
        "py-4",
        "python",
        4,
        "Average time of `x in some_set` is:",
        ("O(1)", "O(log n)", "O(n)", "O(n log n)"),
        0,
        "A set is a hash table, so membership is expected constant time.",
    ),
    _q(
        "py-5",
        "python",
        5,
        "`def f(items=[]):` is a bug because:",
        (
            "The default list is shared across calls that omit the argument",
            "Lists cannot be parameters",
            "The function cannot return",
            "It disables the GIL",
        ),
        0,
        "Default objects are created once, at function definition, and then reused.",
    ),
    _q(
        "sd-1",
        "system_design",
        1,
        "Horizontal scaling means:",
        (
            "Adding more machines",
            "Only buying a larger CPU",
            "Deleting the cache",
            "Turning off replication",
        ),
        0,
        "Scale out by adding nodes. Scaling up means a bigger single machine.",
    ),
    _q(
        "sd-2",
        "system_design",
        2,
        "A cache is used to:",
        (
            "Cut latency and load on the source of truth",
            "Replace durable storage permanently",
            "Guarantee linearizability by itself",
            "Encrypt passwords",
        ),
        0,
        "Caches serve hot reads faster and spare the database, with an invalidation cost.",
    ),
    _q(
        "sd-3",
        "system_design",
        3,
        "Consistent hashing is used to:",
        (
            "Move as few keys as possible when nodes join or leave",
            "Compress HTTP bodies",
            "Sort log files",
            "Replace TLS",
        ),
        0,
        "Keys and nodes sit on a ring so a membership change remaps only a neighboring arc.",
    ),
    _q(
        "sd-4",
        "system_design",
        4,
        "An idempotency key lets a client:",
        (
            "Retry a request without applying the side effect twice",
            "Skip authentication",
            "Pin a deployment forever",
            "Disable timeouts",
        ),
        0,
        "The server stores the key with the result and replays that result on a duplicate retry.",
    ),
    _q(
        "sd-5",
        "system_design",
        5,
        "During a network partition, a CP system will typically:",
        (
            "Refuse some requests to avoid serving inconsistent data",
            "Accept every write and resolve them never",
            "Convert itself into a CDN",
            "Drop encryption",
        ),
        0,
        "CP chooses consistency over availability while the partition lasts.",
    ),
    _q(
        "cc-1",
        "concurrency",
        1,
        "A race condition is when:",
        (
            "The outcome depends on the timing of concurrent operations",
            "A program fails to compile",
            "Two tests share a name",
            "A disk fills up",
        ),
        0,
        "Correctness should not depend on which thread wins the race.",
    ),
    _q(
        "cc-2",
        "concurrency",
        2,
        "A mutex provides:",
        ("Mutual exclusion", "Exactly eight permits", "Lock-free progress always", "Distributed consensus"),
        0,
        "Only one holder enters the critical section at a time.",
    ),
    _q(
        "cc-3",
        "concurrency",
        3,
        "Which is a classic necessary condition for deadlock?",
        ("Circular wait", "A single thread", "Read-only data", "Tail recursion"),
        0,
        "Coffman conditions include mutual exclusion, hold-and-wait, no preemption, and circular wait.",
    ),
    _q(
        "cc-4",
        "concurrency",
        4,
        "A counting semaphore differs from a mutex because it:",
        (
            "Can allow N holders at once",
            "Cannot be released",
            "Is only for processes named N",
            "Removes memory ordering",
        ),
        0,
        "A semaphore has a permit count. A mutex is binary and has an owner.",
    ),
    _q(
        "cc-5",
        "concurrency",
        5,
        "A data race is:",
        (
            "Conflicting accesses, at least one write, without synchronization",
            "Two threads reading one immutable value",
            "Any use of a lock",
            "A deadlock of two mutexes",
        ),
        0,
        "Data races are unsynchronized conflicting accesses. Deadlock is a different failure.",
    ),
)


class QuestionBank:
    def __init__(self, questions: tuple[Question, ...] | list[Question] = QUESTIONS) -> None:
        self._questions = tuple(questions)
        self._by_id = {question.id: question for question in self._questions}
        if len(self._by_id) != len(self._questions):
            raise ValueError("duplicate question ids")

    def get(self, question_id: str) -> Question:
        try:
            return self._by_id[question_id]
        except KeyError as exc:
            raise KeyError(question_id) from exc

    def for_topic(self, topic: str) -> tuple[Question, ...]:
        return tuple(question for question in self._questions if question.topic == topic)

    def topics(self) -> tuple[str, ...]:
        return tuple(TOPICS)
