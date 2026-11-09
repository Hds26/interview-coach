"""Local STAR prompts. Stems are Chinese; English is optional coach context."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StarItem:
    id: str
    tags: tuple[str, ...]
    prompt: str
    stem_en: str
    example: tuple[str, str, str, str]


def _item(
    item_id: str,
    tags: tuple[str, ...],
    prompt: str,
    stem_en: str,
    situation: str,
    task: str,
    action: str,
    result: str,
) -> StarItem:
    return StarItem(item_id, tags, prompt, stem_en, (situation, task, action, result))


STAR_ITEMS: tuple[StarItem, ...] = (
    _item(
        "star-conflict-release",
        ("冲突", "压力"),
        "上线前一天，你和同事对实现方案意见相反，发布时间又不能再拖。用 STAR 讲你怎么处理。",
        "The day before release you and a teammate disagreed, and the date could not move.",
        "上个季度我在支付团队负责结算服务，上线前一天和同事对方案发生冲突。",
        "我的目标是当天选定一个能回滚的方案，不能把发布时间再往后推。",
        "我先把两边的差异写成对照，再拉产品对齐，并给新路径加上开关和日志 log。",
        "发布按时完成，回滚次数从 2 次降到 0。如果下次重来，我会更早把数字写进评审。",
    ),
    _item(
        "star-collab-cross-team",
        ("协作", "场景"),
        "一个需求要跨两个团队才能上线，对方排期已经排满。用 STAR 讲你怎么把事情推进下去。",
        "A change needed two teams, and the other team was already fully booked.",
        "上个季度我在订单团队负责库存服务，另一个团队的排期已经排满，功能还是要一起上线。",
        "我的目标是两周内打通库存校验，不能让大促期间超卖。",
        "我先把接口契约写成对照，再约对方对齐最小范围，自己实现了开关和日志 log。",
        "超卖从每天 30 单降到 0。如果下次重来，我会在排期会上先把依赖说死。",
    ),
    _item(
        "star-failure-outage",
        ("失败", "责任"),
        "你改过的代码引起了一次线上故障。用 STAR 讲当时发生了什么，以及你做了什么。",
        "A change you shipped caused a production incident.",
        "上个季度我在支付团队负责对账服务，一次发布后出现了线上事故。",
        "我的目标是在一小时内恢复写入，不能让对账延迟继续扩大。",
        "我先对照发布差异，再把开关关掉并留下日志 log，同时拉测试对齐影响面。",
        "错误率从 12% 降到 0。如果下次重来，我会先看指标再放量。",
    ),
    _item(
        "star-lead-unowned",
        ("领导力", "责任"),
        "有一个影响用户的问题，没有明确的负责人。用 STAR 讲你怎么把人组织起来。",
        "A user-facing problem had no owner. How did you organize people?",
        "上个季度我在平台团队负责账号服务，用户登录失败却没有明确的负责人。",
        "我的目标是当天恢复登录，不能让故障过夜。",
        "我先拉相关同学对齐分工，自己排查开关和日志 log，并写下对照表。",
        "登录成功率从 92% 提升到 99%。如果下次重来，我会先指定一个临时负责人。",
    ),
    _item(
        "star-scenario-ambiguous",
        ("场景", "沟通"),
        "需求文档很短，产品和研发对「做完」的理解不一样。用 STAR 讲你怎么把范围说清。",
        "The spec was thin, and product and engineering disagreed on what done meant.",
        "上个季度我在增长团队负责优惠券服务，需求只有几行，两边对上线标准不一致。",
        "我的目标是本周内写清验收，不能带着开放问题进入开发。",
        "我先把争议点做成对照，再和产品对齐三条验收，并给例外路径加了开关和日志 log。",
        "返工从 4 次降到 1 次。如果下次重来，我会把验收贴在需求正文里。",
    ),
    _item(
        "star-conflict-priority",
        ("冲突", "取舍"),
        "两个都标了高优先级的需求撞在同一周，你不可能都做完。用 STAR 讲你怎么取舍。",
        "Two high-priority requests landed in the same week and you could not finish both.",
        "上个季度我在计费团队负责账单服务，同一周有两个都标了高优的需求。",
        "我的目标是保住账单按时出账，不能两个需求都承诺本周上线。",
        "我先用流量和金额做对照，再和产品对齐取舍，只给选中的那条加开关和日志 log。",
        "出账延迟从 6 小时降到 1 小时。如果下次重来，我会更早公开没做的那一条。",
    ),
    _item(
        "star-collab-review",
        ("协作", "冲突"),
        "设计评审里，一位同事坚持要推翻你的方案。用 STAR 讲你怎么回应，最后怎么定的。",
        "In review, a teammate wanted to throw out your design.",
        "上个季度我在推荐团队负责召回服务，评审时一位同事坚持推翻原方案。",
        "我的目标是当天定下一个可上线的方案，不能把评审拖成无限讨论。",
        "我先把两个方案写成对照，再用一份指标对齐取舍，并给选定方案加上日志 log。",
        "评审从 3 轮降到 1 轮，延迟下降 40%。如果下次重来，我会提前把约束发给评审人。",
    ),
    _item(
        "star-failure-estimate",
        ("失败", "成长"),
        "你把一个任务估成三天，实际做了两周。用 STAR 讲你怎么发现偏差，以及怎么收场。",
        "You estimated three days and it took two weeks.",
        "上个季度我在基础架构团队负责迁移服务，一个任务我估了三天，两周还没结束。",
        "我的目标是把剩余工作在下周交付，不能继续按原来的三天承诺对外同步。",
        "我先把未完成项做成对照，再和需求方对齐新的范围，并为迁移加上开关和日志 log。",
        "剩余工作从 14 天降到 5 天完成。如果下次重来，我会把未知依赖单独估时。",
    ),
    _item(
        "star-lead-junior",
        ("领导力", "协作"),
        "你带一位新人做一块你熟悉的功能，进度一度落后。用 STAR 讲你怎么帮对方赶上。",
        "You were mentoring a new teammate whose feature fell behind.",
        "上个季度我在商家团队负责店铺服务，我带的新人进度落后了一周。",
        "我的目标是让他在迭代内独立交付，不能改成我替他写完。",
        "我先和他对齐最小切片，再让他实现开关，我只帮他看日志 log 和对照用例。",
        "延期从 5 天降到 0，他独立合入 3 个变更。如果下次重来，我会更早每天看一次指标。",
    ),
    _item(
        "star-scenario-oncall",
        ("场景", "压力"),
        "你值班时告警响了，用户已经能看到错误。用 STAR 讲那一个小时你做了什么。",
        "You were on call, the alert fired, and users could see errors.",
        "上个季度我在交易团队负责下单服务，值班时告警响起，用户已经看到错误。",
        "我的目标是 30 分钟内止住错误，不能在原因没查清时继续放量。",
        "我先看指标和日志 log，再关掉新代码的开关，并拉值班同学对齐公告。",
        "错误率从 8% 降到 0.1%。如果下次重来，我会把回滚开关练到不用想。",
    ),
    _item(
        "star-growth-feedback",
        ("成长", "沟通"),
        "有人当面向你指出一个你不爱听的工作习惯。用 STAR 讲你后来改了什么。",
        "Someone told you, face to face, about a habit you did not want to hear.",
        "上个季度我在数据团队负责报表服务，同事当面说我评审时只讲结论、不讲依据。",
        "我的目标是下一次评审让对方能核对依据，不能再用「我觉得」把讨论关掉。",
        "我先把上次评审做成对照，再在新方案里写上指标和日志 log，并提前发给同事对齐。",
        "评审来回从 4 轮降到 2 轮。如果下次重来，我会把依据放在第一段。",
    ),
    _item(
        "star-failure-rollback",
        ("失败", "责任"),
        "一次发布之后你决定回滚。用 STAR 讲你为什么回滚，以及回滚之后做了什么。",
        "After a release you decided to roll back.",
        "上个季度我在运维平台团队负责发布服务，一次上线后核心指标变差，我决定回滚。",
        "我的目标是 15 分钟内回到上一版本，不能一边回滚一边继续灰度。",
        "我先按对照表关掉开关，再执行回滚并盯着日志 log，随后和值班对齐影响面。",
        "延迟从 900ms 降到 220ms。如果下次重来，我会把回滚条件写进发布单。",
    ),
)

_BY_ID = {item.id: item for item in STAR_ITEMS}


def star_items() -> tuple[StarItem, ...]:
    return STAR_ITEMS


def get_item(item_id: str) -> StarItem:
    try:
        return _BY_ID[item_id]
    except KeyError as exc:
        raise ValueError(f"unknown STAR item {item_id}") from exc
