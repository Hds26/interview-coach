# Interview Study Coach

离线优先的 Python 面试学习教练。用自适应题目（选择题和开放题）摸清短板，按每天约 30 分钟生成 7 天计划（每天都有可核对的验收标准，开放题走本地 rubric），记录完成情况，再按完成率重排下一周。也可以按间隔把薄弱题提前带回下一周，而不必只靠整周重排。默认不调用任何模型 API。

Offline-first CLI for interview prep. It estimates what you know with adaptive multiple-choice and open questions, builds a 7-day plan at about 30 minutes a day with measurable acceptance criteria, tracks what you finish, and replans from that completion rate. Due topics can also move to the front of the next week. No API key is required.

## 安装 / Install

Python 3.11 or newer.

```bash
pip install -e ".[dev]"
pytest
interview-coach demo
```

The same demo is available as a module:

```bash
PYTHONPATH=src python -m interview_coach demo
```

SQLite files go under `data/` (`data/coach.sqlite` for normal use, `data/demo.sqlite` for the demo). Override the path with `--db` or `INTERVIEW_COACH_DB`.

## 命令 / Commands

```bash
interview-coach profile init --name Ada --role "Backend engineer" --target backend_engineer --daily-minutes 30
interview-coach profile show
interview-coach targets
interview-coach topics
interview-coach assess --questions 12
interview-coach assess --topics python --kinds open --questions 1 --answers "|created once and shared mutable list|"
interview-coach assess --tags gil --kinds mcq --questions 1 --answers 0
interview-coach plan
interview-coach due
interview-coach drill --questions 4 --answers 0,1,0,1
interview-coach log --day 1 --minutes 30 --quiz 8/10
interview-coach log --day 2 --minutes 0 --missed
interview-coach progress
interview-coach replan
interview-coach export --format both --out data/week
interview-coach import practice.json
interview-coach ask "what should I study today"
```

`assess` 和 `drill` 在交互终端里提问。非交互时用 `--answers`：选择题写 `0,2,A`，开放题写 `|your answer|`（答案里不要加逗号）。`--topics python,databases` 限制主题，`--kinds mcq` 或 `--kinds open` 限制题型，`--tags hashing,mvcc` 只抽带这些标签的题。`--answers` 的顺序必须和自适应抽到的题目一致；选择题和开放题混在一起时，脚本更稳妥的做法是用 `--kinds` 分开跑。

`assess` and `drill` are interactive on a terminal. Pass `--answers 0,2,A` for multiple choice, and `--answers "|your answer|"` for an open item (no commas inside the text). `--topics`, `--kinds`, and `--tags` narrow the pool. The answer list has to follow the adaptive draw, so script mixed sessions with `--kinds` instead of guessing which item comes next. `drill` practices topics that are due and does not replace the active week. `--on` only decides which topics are due; the next review is still scheduled from today.

`--role` 是职位名称，原文保存。`--target` 选择权重预设；省略时是 `generic_tech`（各主题权重相同）。`--target auto` 才会根据职位名称推断。

`--role` stores the job title as written. `--target` selects a weight preset. The default `generic_tech` keeps every weight at 1. `--target auto` infers a preset from the job title.

预设 / presets: `generic_tech`, `backend_engineer`, `frontend_engineer`, `data_engineer`, `python_exam`, `system_design_exam`. 后两个是考试模式的权重桩，不会新增题库分区。`frontend_engineer` 和 `data_engineer` 同样只调整现有主题的权重。

`export --format md` 或 `ics` 把当前周写到文件；省略 `--out` 则打印到标准输出。`--format both --out data/week` 会写出 `data/week.md` 和 `data/week.ics`。

`import` 读取本地 JSON 或 CSV，不访问网络。练习行更新能力估计；如果文件里有日志行，则记到当前计划。

```json
{
  "practice": [{"topic": "python", "difficulty": 3, "correct": true}],
  "logs": [{"day": 1, "minutes": 30, "completed": true, "quiz": "8/10"}]
}
```

```csv
topic,difficulty,score
databases,4,0.5
```

单独一个 JSON 数组也视为练习行。A bare JSON list is treated as practice rows.

## 行为 / Behavior

- **Assessment.** 每个主题有 1 到 5 的能力值。答对会升高，下一题更难；答错则相反。开放题用本地 rubric 打 0 到 1 的部分分，同样更新能力值。目标预设会改变抽题比例：权重高的主题被抽到的次数更多。分数存在 SQLite。
- **Confidence.** 每道题按难度带一个固定区分度。信息量近似 `区分度² × p × (1 − p)`，`p` 是当前能力下的期望得分。把握度是 `信息量 / (信息量 + 1)`，不是训练出来的模型。题目难度越接近当前能力，单题贡献的把握度越高。
- **Open answers.** 每个主题有一道开放题。验收标准里写了题号和需要命中的 rubric 点数。评分只做关键词匹配，不调用模型。
- **Tags.** 题目带标签。`topics` 会列出每个主题的标签，`assess --tags` 按标签过滤，自适应选题仍然有效。
- **Profile.** 一位学习者、一个职位字符串、一个目标预设、每天分钟数。默认 30 分钟（允许 10–180）。`generic_tech` 不改变原来的能力排序。
- **Plan.** 七天。更弱、或在当前目标下权重更高的主题排在前面。第 1–5 天是专项，第 6 天混合复习，第 7 天限时模拟。每天都有数字验收标准，其中包括一道本地 rubric 开放题。
- **Spaced review.** 练过的主题会得到 `next_review`：能力越低，间隔越短（1、2、4、7 或 14 天）。`due` 列出到期主题。`replan` 在 steady / stretch 时把到期主题排到未完成主题之前，所以薄弱点不用干等整周重排。shrink（完成率低于 60%）仍只盯最弱的三个主题。`drill` 只练习到期主题，不新建一周计划。
- **Replan.** 完成率是已记录天数里的 `done / (done + missed)`。低于 60% 则收缩（3 个最弱主题、更易的检查、少 5 分钟，最低 10）。至少 85% 完成且测验正确率至少 70% 则加码（更难的检查、多 5 分钟，最高 120）。其余情况保持分钟数，并把未完成主题和到期主题往前排。
- **Import / export.** JSON 与 CSV 导入练习和日志。Markdown 与 ICS 导出当前周，方便放进日历。核心路径都不需要 API key。
- **Coach.** `ask` 走一个 agent 循环：系统提示加本地工具（`get_profile`, `get_scores`, `get_plan`, `get_progress`, `get_today`）。默认 `--llm offline` 只用这些工具结果写回复。`--llm openai` 复用同一套工具，需要 `OPENAI_API_KEY` 和 `pip install -e ".[llm]"`。

## 布局 / Layout

```
src/interview_coach/
  assessment/   question bank, open rubrics, adaptive session, scoring, target weights
  profile/      name, job title, target preset, daily minutes
  planner/      7-day plan and replan policy
  tracker/      completion, spaced review, JSON/CSV import, Markdown/ICS export
  agent/        prompts, local tools, offline and OpenAI clients
  cli.py        interview-coach entry point
  demo.py       scripted week
data/           SQLite databases
tests/          pytest
```

## 测试 / Tests

```bash
pip install -e ".[dev]"
pytest
```
