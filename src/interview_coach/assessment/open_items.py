"""Open prompts. Scored locally by rubric keywords, in Chinese or English.

Each topic has more than one prompt so a repeated day does not have to ask
the same open item. The first item of each topic keeps the original id.
"""

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
        "动态哈希表一边变大，为什么期望查找还能保持便宜？",
        "负载因子有上限，冲突有办法处理，几何扩容把偶尔的整表拷贝摊到很多次插入上。",
        ("hashing", "amortized"),
        (
            _point("提到负载因子或桶的填充程度", "负载因子", "装填因子", "load factor", "fullness"),
            _point("说到冲突的处理办法", "拉链", "开放寻址", "冲突", "chaining", "probing", "collision"),
            _point("说明扩容对很多次插入是便宜的", "均摊", "翻倍", "扩容", "amortized", "doubling", "resize"),
        ),
    ),
    _open(
        "ah-open-2",
        "arrays_hashing",
        4,
        "静态数组上的区间和，为什么前缀和常常比线段树更合适？",
        "数组不再修改时，一次线性预处理之后，任意区间和都是两次前缀相减。",
        ("arrays", "prefix-sum"),
        (
            _point("数组是静态的，或建好后不再改", "静态", "不再改", "不会更新"),
            _point("问的是区间和", "区间和", "子数组和"),
            _point("查询是常数时间或只需相减", "常数", "O(1)", "相减"),
        ),
    ),
    _open(
        "tg-open",
        "trees_graphs",
        4,
        "什么时候选 Dijkstra，而不是普通的广度优先搜索？",
        "边带权并且权值都非负时用 Dijkstra 求最短路。无权图数跳数用 BFS。",
        ("graphs", "shortest-path"),
        (
            _point("图或边是带权的", "带权", "权重", "weighted"),
            _point("权值必须非负", "非负", "没有负", "non-negative", "nonnegative", "no negative"),
            _point("目标是最短路径", "最短路径", "最短路", "shortest path", "shortest-path"),
        ),
    ),
    _open(
        "tg-open-2",
        "trees_graphs",
        2,
        "为什么广度优先搜索能求出无权图上的最短路？",
        "每条边代价相同，队列按层扩展，第一次到达一个点用的边数就是最少的。",
        ("graphs", "bfs"),
        (
            _point("边权相同或图是无权的", "无权", "权相同", "边权相同"),
            _point("用队列一层层扩展", "队列", "一层"),
            _point("第一次到达就是最短", "第一次", "最少", "最短"),
        ),
    ),
    _open(
        "cx-open",
        "complexity",
        2,
        "为什么二分查找是对数时间，而不是线性？",
        "数组必须有序。每次比较都丢掉剩下的一半，所以深度是 log n。",
        ("search", "logarithms"),
        (
            _point("输入必须有序", "有序", "已经排序", "sorted"),
            _point("每一步丢掉一半", "一半", "减半", "half", "halves"),
            _point("所以是对数时间", "对数", "log", "logarithmic"),
        ),
    ),
    _open(
        "cx-open-2",
        "complexity",
        3,
        "动态数组偶尔要把整表拷贝一遍，为什么不能说每次插入都是 O(n)？",
        "扩容按倍数增长，每个元素被拷贝的次数是常数，一串插入的总代价是线性的，单次是均摊常数。",
        ("amortized", "arrays"),
        (
            _point("贵的拷贝只是偶尔发生", "偶尔", "不是每次"),
            _point("容量按倍数增长", "翻倍", "两倍", "倍数"),
            _point("用均摊来看单次代价", "均摊", "摊还"),
        ),
    ),
    _open(
        "db-open",
        "databases",
        4,
        "MVCC 给读者和写者解决了什么问题？",
        "它保留多个版本，读者看快照，写者写新版本，两边不用互相堵住。",
        ("transactions", "mvcc"),
        (
            _point("提到快照或一致的视图", "快照", "snapshot"),
            _point("读不必堵住写", "不阻塞", "不会阻塞", "do not block", "don't block", "without blocking", "does not block"),
            _point("提到行的多个版本", "版本", "version"),
        ),
    ),
    _open(
        "db-open-2",
        "databases",
        3,
        "覆盖索引为什么常常能少一次回表？",
        "查询要用的列已经在索引里，引擎不必再按主键去表里取整行。",
        ("indexes", "covering"),
        (
            _point("需要的列已经在索引里", "索引", "列都在"),
            _point("因此不用回表", "回表", "不用再读表"),
            _point("少了一次随机读", "随机", "IO", "I/O"),
        ),
    ),
    _open(
        "net-open",
        "networking",
        3,
        "TCP 三次握手在真正发数据之前建立了什么？",
        "SYN、SYN-ACK、ACK 把连接打开，并交换起始序号。",
        ("tcp",),
        (
            _point("说出 SYN 这一段交换", "syn", "SYN"),
            _point("连接被建立起来", "连接", "connection"),
            _point("提到序号或确认", "序号", "确认", "sequence", "acknowledg"),
        ),
    ),
    _open(
        "net-open-2",
        "networking",
        4,
        "TLS 保护传输上的什么，又不管应用里的什么？",
        "它提供机密性和完整性，并校验证书。用户有没有权做某件业务，是应用自己判断的。",
        ("tls", "security"),
        (
            _point("传输内容保密", "加密", "机密", "保密"),
            _point("传输内容防篡改", "完整", "篡改"),
            _point("不管业务上的授权", "授权", "权限", "业务"),
        ),
    ),
    _open(
        "py-open",
        "python",
        4,
        "为什么 `def f(items=[])` 这种可变默认参数是个坑？",
        "默认对象在函数定义时只创建一次，之后省略参数的调用都共享它。",
        ("functions", "mutability"),
        (
            _point("默认参数只创建一次", "只创建一次", "定义时", "创建一次", "once", "definition time", "defined once"),
            _point("之后的调用共享这个对象", "共享", "被复用", "同一个列表", "shared", "reused", "same list"),
            _point("这个对象是可变的", "可变", "列表", "mutable", "list"),
        ),
    ),
    _open(
        "py-open-2",
        "python",
        5,
        "有 GIL 的时候，什么样的工作仍然值得开多线程？",
        "等待 IO 时很多 C 扩展会放开 GIL，线程能重叠等待。吃满 CPU 的计算更适合多进程。",
        ("gil", "concurrency"),
        (
            _point("工作在等 IO", "IO", "I/O", "网络", "磁盘"),
            _point("等待时会放开 GIL", "放开", "释放"),
            _point("吃 CPU 的计算更适合多进程", "多进程", "进程", "CPU"),
        ),
    ),
    _open(
        "sd-open",
        "system_design",
        5,
        "客户端重试一次写请求时，幂等键保住了什么？",
        "服务端记住这个键和当时的结果，重试不会把副作用再做一遍。",
        ("reliability", "idempotency"),
        (
            _point("提到重试", "重试", "retry", "retries"),
            _point("不能把副作用做两遍", "重复", "两次", "duplicate", "twice", "second time"),
            _point("记住结果或那个副作用", "副作用", "结果", "side effect", "result"),
        ),
    ),
    _open(
        "sd-open-2",
        "system_design",
        4,
        "缓存穿透和缓存击穿差在哪里？各用什么挡住？",
        "穿透是在查根本不存在的键，可以用空值或布隆过滤器。击穿是热点键刚好过期，可以用单飞锁住回源。",
        ("caching",),
        (
            _point("穿透是键不存在", "不存在", "穿透"),
            _point("击穿是热点过期", "热点", "过期", "击穿"),
            _point("说出一种挡住的办法", "布隆", "空值", "单飞", "锁"),
        ),
    ),
    _open(
        "cc-open",
        "concurrency",
        3,
        "说出一条死锁的 Coffman 条件，以及它为什么重要。",
        "循环等待、互斥、持有并等待、不可抢占，四条凑齐才可能死锁。打破其中一条就能防住。",
        ("deadlock", "locks"),
        (
            _point(
                "说到死锁或一条 Coffman 条件",
                "死锁",
                "循环等待",
                "持有并等待",
                "deadlock",
                "circular wait",
                "hold-and-wait",
                "hold and wait",
            ),
            _point("提到互斥或锁", "互斥", "锁", "mutual exclusion", "mutex", "lock"),
            _point("这条条件和死锁怎么形成或怎么避免有关", "条件", "避免", "预防", "condition", "prevent", "avoid"),
        ),
    ),
    _open(
        "cc-open-2",
        "concurrency",
        3,
        "约定全局加锁顺序，打破的是哪条死锁条件？",
        "固定顺序让等待图成不了环，打破的是循环等待。",
        ("deadlock", "locks"),
        (
            _point("点出循环等待", "循环等待", "成环", "循环"),
            _point("大家都按同一个顺序拿锁", "顺序", "先拿"),
            _point("因此死锁这条路被堵上", "死锁", "堵", "避免"),
        ),
    ),
)


def open_questions_for(topic: str) -> tuple[Question, ...]:
    return tuple(question for question in OPEN_QUESTIONS if question.topic == topic)


def open_question_for(topic: str) -> Question | None:
    items = open_questions_for(topic)
    return items[0] if items else None
