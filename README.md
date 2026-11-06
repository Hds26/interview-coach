# Interview Study Coach

离线优先的面试教练。每天一条命令：看今天练什么，做一套短练习，达标就自动记完成。

Offline-first interview coach. One command a day: see the plan, do a short session, and log the day when the checks pass.

## 每天就这一条 / The daily command

Python 3.11 or newer.

```bash
pip install -e ".[dev]"
interview-coach profile init --name Ada --role "Backend engineer"
interview-coach today
```

`interview-coach` 和 `interview-coach go` 跟 `interview-coach today` 是同一条命令。

`interview-coach` and `interview-coach go` are the same command.

它会：

1. 没有 7 天计划时，按当前水平自动排好。
2. 用几句话说明接下来约 30 分钟练什么，以及 2–3 条验收标准。
3. 做一套短练习（默认 5 题，每个主题一轮最多 6 题）。答错会显示题目里的说明。
4. 验收标准达到后自动记下这一天，不用再运行 `log`。
5. 用两三句中文说下一步。`--lang en` 换成英文。

教练默认说中文。弱项用大白话，不先甩掌握百分比。

The coach speaks Chinese by default. Weak topics are named in plain language; mastery percents stay in the background. Pass `--lang en` for English.

第一次没有画像时，它会告诉你唯一需要的初始化命令，不会先问一长串问题。每天时长默认 30 分钟。连续目标和题型有默认值，只在你想改的时候再加：

```bash
interview-coach profile init --name Ada --role "Backend engineer" --daily-minutes 30 --streak-goal 5 --kinds mcq,open
```

`--role` 是职位名称，原文保存。`--target` 选择权重预设；省略时是 `generic_tech`。`--target auto` 才会根据职位名称推断。

再次运行 `profile init` 只改名字、职位和这些偏好，**不会清空**能力分、做题记录和计划。确定要重算能力分时才加 `--reset`（计划仍保留）。

Running `profile init` again renames the profile and updates preferences. It does not wipe ability scores, answer history, or the plan. `--reset` clears ability scores and leaves the plan in place.

SQLite 在 `data/coach.sqlite`。可以用 `--db` 或 `INTERVIEW_COACH_DB` 换路径。

## 练习时怎么作答 / Answering

在终端里直接作答。脚本或管道里用 `--answers`：选择题写 `0,2,A`，开放题写 `|your answer|`（答案里不要加逗号）。

开放题按要点打分，认的是词，不是随便一段子串。`sorted` 不会因为出现在 `unsorted` 里就算对，`log` 也不会命中 `catalog`。评分在本地完成，不调用模型。当天的开放题会留在这组练习的最后一题。

Open answers are scored offline against the point rubric, token by token. A keyword has to stand on its own; `log` does not match inside `catalog`.

同一道题做完一轮后，下次不会立刻再抽到，除非题库用完，或者这道题到了复习日。看到的题记在 SQLite 里。

Seen items are stored in SQLite and are not served again until that pool is exhausted or the item is due for review.

## 其他命令 / Other commands

日常不需要记这些。原来的命令都还在。

```bash
interview-coach profile show
interview-coach targets
interview-coach topics
interview-coach assess --questions 12
interview-coach plan
interview-coach due
interview-coach drill --questions 4
interview-coach log --day 1 --minutes 30 --quiz 8/10
interview-coach progress
interview-coach replan
interview-coach export --format both --out data/week
interview-coach import practice.json
interview-coach ask "今天练什么"
interview-coach demo
```

`assess` 和 `drill` 达标时同样会自动记下当天，只要这一天的计划还没完成、练的就是这一天的主题。`drill` 只练到期主题。没有到期主题时它什么都不改，也不会重排复习日。

`drill` only practices topics that are due. If nothing is due, it leaves the schedule alone.

`demo` 会在目标数据库已存在时停下来。确认覆盖再加 `--yes`：

```bash
interview-coach demo --db data/demo.sqlite --yes
```

`--topics`、`--kinds`、`--tags` 用来缩小 `assess` 的范围。`--answers` 的顺序必须和抽到的题目一致；选择题和开放题混在一起时，用 `--kinds` 分开跑更稳。

`export --format md` 或 `ics` 导出当前周。`import` 只读本地 JSON 或 CSV，不访问网络。

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

预设 / presets: `generic_tech`, `backend_engineer`, `frontend_engineer`, `data_engineer`, `python_exam`, `system_design_exam`. 后两个是考试模式的权重桩，不会新增题库分区。

## 模型 / LLM

默认不调用任何模型。`ask` 和 `today` 的离线回复只来自本地数据库。

DeepSeek 仍然只从环境变量读密钥。设置 `DEEPSEEK_API_KEY` 后：

```bash
interview-coach ask "今天练什么" --llm deepseek
```

DeepSeek 使用官方 OpenAI 兼容接口 `POST https://api.deepseek.com/chat/completions`。当前文档（<https://api-docs.deepseek.com/>）列出的模型是 `deepseek-flash` 和 `deepseek-v4-pro`。`deepseek-chat` 已停用，因此默认模型是 `deepseek-flash`，并关闭 thinking。`ask` 仍走本地工具循环：`get_profile`、`get_scores`、`get_plan`、`get_progress`、`get_today`。系统提示要求短句、先给结论、只引用工具返回的数据，不编造分数。

DeepSeek calls `POST https://api.deepseek.com/chat/completions`. The default model is `deepseek-flash` with thinking disabled. The system prompt asks for short sentences, a conclusion first, and no invented scores.

可选环境变量：`DEEPSEEK_MODEL`（默认 `deepseek-flash`）、`DEEPSEEK_BASE_URL`（默认 `https://api.deepseek.com`，必须是 https）。

没有 `DEEPSEEK_API_KEY` 时，`--llm deepseek` 以退出码 1 结束，并且不会发出请求。密钥只放在环境变量里。可以把 `.env.example` 复制为本地 `.env` 再自己 `export`；程序不会自动加载 `.env`。`.env` 已在 `.gitignore` 中。`.env.example` 只有空的 `DEEPSEEK_API_KEY=`。不要把真实 key 提交到 git，也不要写进 README、issue 或示例命令。

When `DEEPSEEK_API_KEY` is missing, `--llm deepseek` exits with code 1 and sends no request. Keep the key in the environment. Copy `.env.example` to a local `.env` and export it yourself; the program does not load `.env`. Never commit a real key.

`--llm openai` 需要 `OPENAI_API_KEY` 和 `pip install -e ".[llm]"`。DeepSeek 使用标准库发 HTTP，安装 `.[dev]` 即可跑测试和离线命令。

## 行为 / Behavior

- **Today.** 一条命令完成「看计划 → 短练习 → 达标自动打卡 → 下一步」。没有计划会自动建；这一周都记完了，下一次会按完成率排下一周。
- **Assessment.** 每个主题能力值 1 到 5。答对升高，答错降低。开放题用本地 rubric 打 0 到 1 的部分分。每个主题一轮最多 6 题。
- **Exposure.** 做过的题会记下。同一题不会在下一轮立刻出现，除非这个范围内的题都见过，或者这道题到了复习日。
- **Confidence.** 信息量近似 `区分度² × p × (1 − p)`。把握度是 `信息量 / (信息量 + 1)`。这些数字还在 `progress` 里，教练开口时不拿它们当第一句话。
- **Profile.** 一位学习者、一个职位、一个目标预设、每天分钟数。默认 30 分钟（允许 10–180）。可选连续目标（默认 5）和偏好题型（默认选择题加开放题）。
- **Plan.** 七天。更弱、或权重更高的主题排在前面。每天都有可核对的验收标准。
- **Auto-log.** `today`、`assess`、`drill` 练的是当前未完成的那一天，并且分数和开放题要点都达到标准时，自动把这一天记为完成。
- **Spaced review.** 练过的主题会得到 `next_review`。`due` 列出到期主题。`replan` 在 steady / stretch 时把到期主题往前排。
- **Replan.** 完成率低于 60% 则收缩。至少 85% 完成且测验正确率至少 70% 则加码。其余保持分钟数。
- **Coach.** `ask` 先说接下来约 30 分钟做什么，再给 2–3 条验收标准，最后用大白话点弱项。
- **STAR.** 行为面试（STAR）还没做。以后可以加一个单独练习，不影响现在的每日命令。

## 布局 / Layout

```
src/interview_coach/
  assessment/   question bank, open rubrics, adaptive session, scoring, target weights
  profile/      name, job title, target preset, daily minutes, optional streak and item types
  planner/      7-day plan, acceptance checks, replan policy
  tracker/      completion, spaced review, seen items, JSON/CSV import, Markdown/ICS export
  agent/        prompts, local tools, offline, OpenAI, and DeepSeek clients
  cli.py        interview-coach entry point
  demo.py       scripted week; asks before replacing a database
data/           SQLite databases
tests/          pytest
```

## 测试 / Tests

```bash
pip install -e ".[dev]"
pytest
```
