# Interview Study Coach

离线优先的面试教练。每天一条命令：看今天练什么，做一套短练习，达标就自动记完成。

Offline-first interview coach. One command a day: see the plan, do a short session, and log the day when the checks pass.

## 每天就这一条 / The daily command

Python 3.11 or newer.

```bash
pip install -e ".[dev]"
interview-coach start --name Ada --role 后端
interview-coach today
```

`interview-coach` 和 `interview-coach go` 跟 `interview-coach today` 是同一条命令。

`interview-coach` and `interview-coach go` are the same command.

它会：

1. 没有 7 天计划时，按当前水平自动排好。
2. 用几句话说明接下来约 30 分钟练什么，以及 2–3 条验收标准。
3. 做一套短练习（默认 5 题，每个主题一轮最多 6 题）。题目、选项和说明都是中文。答错会显示题目里的说明。
4. 验收标准达到后自动记下这一天，不用再运行 `log`。记下的分钟数是这次实际用时，不是计划里的 30 分钟。
5. 用两三句中文说下一步。`--lang en` 只把教练的话换成英文，题目仍是中文。

教练默认说中文。弱项只来自已经做错的题，不先甩掌握百分比，也不会把还没练过的主题说成薄弱。

The coach speaks Chinese by default, and so do the questions. `--lang en` switches the coach copy to English; the items stay Chinese. A topic is called weak only after a wrong or partial answer.

第一次没有画像时，运行 `interview-coach start`。它只问名字、职位、每天几分钟、练习方式、自评薄弱主题，也可以直接用参数一次写完。每天时长默认 30 分钟。连续打卡按完成的日历日计算；跳过一天，连续天数会断，过期没做的日子会记为错过。

```bash
interview-coach profile init --name Ada --role "后端" --daily-minutes 30 --streak-goal 5 --kinds mcq,open
interview-coach today --kinds mcq
```

`--role` 是职位名称，原文保存。第一次省略 `--target` 时按职位推断：`后端` 和 `Backend engineer` 都是 `backend_engineer`，第一天练数据库。明确写 `--target generic_tech` 才是等权重，第一天从数组和哈希开始。`--target auto` 同样按职位推断。

再次运行 `profile init` 时，省略 `--level`、`--daily-minutes` 或 `--target` 会**保留**原来的值，不会写回 mid、30 分钟和 `generic_tech`。它只改你写出来的名字、职位和偏好，**不会清空**能力分、做题记录和计划。确定要重算能力分时才加 `--reset`（计划仍保留）。

Running `profile init` again updates the name, role, and any preference you pass. Omit `--level`, `--daily-minutes`, or `--target` to keep the saved values. It does not wipe ability scores, answer history, or the plan. `--reset` clears ability scores and leaves the plan in place.

SQLite 在 `data/coach.sqlite`。可以用 `--db` 或 `INTERVIEW_COACH_DB` 换路径。

## 第一次：学习画像 / Onboarding

`start` 把习惯、自评和可选的简历或职位说明记进 SQLite，并排出 7 天计划和验收标准。之后每天仍然是 `today`。

```bash
interview-coach start --name Ada --role 后端 --daily-minutes 25 --kinds 开放题 --weak 网络 --paste-jd <<'EOF'
后端岗位，使用 Redis 和 MySQL。
EOF
interview-coach today
```

终端里直接运行 `interview-coach start` 会问那几项。简历和职位说明也可以用 `--resume-file` 和 `--jd-file` 同时传入。原文不入库，只留下映射到本地主题的技能名。

自评和职位说明只决定先练什么，不会写成能力分，也不会被说成「已经证明的薄弱项」。已经做过的题如果和它们冲突，以做题记录为准。没有密钥时全程离线。`--llm deepseek` 只在设置了 `DEEPSEEK_API_KEY` 时帮忙收技能名，失败就用本地词表。

`profile init` 仍可单独改名字和职位。`start` 不会清空做题记录。

## 可选：按职位说明加重 / Optional research

这不是每天的命令。`today` / `go` 不会联网，也不要求先做 research。

```bash
interview-coach research --paste <<'EOF'
后端岗位，使用 Redis 和 MySQL。
EOF
interview-coach research --show
interview-coach research --clear
```

`--paste` 从标准输入读职位说明或笔记，映射到本地主题，生成最多 5 道中文草稿。终端里会先预览，确认 `y` 才写入；直接回车或在脚本里不写 `--yes` 则什么都不写，计划不变。原文不入库，只留下技能标签、生成的题干、来源标题和链接。

权重在大约 7 天内提高，30 天后不再计入。它只影响接下来练什么，不会把这些主题说成薄弱项，也不会重写整周。

`interview-coach research 公司 岗位` 只做一次公开检索。失败、过旧、广告，或结果落在登录墙后面时，提示改用 `--paste`。不会去抓 Boss、拉勾、LinkedIn、牛客或 Glassdoor。

有 `DEEPSEEK_API_KEY` 时可以加 `--llm deepseek` 帮忙收技能名。没有密钥或调用失败就用本地抽取，不需要密钥。

## 练习时怎么作答 / Answering

在终端里直接作答。脚本或管道里用 `--answers`：选择题写 `0,2,A`，开放题写 `|your answer|`（答案里不要加逗号）。

开放题按要点打分，中文短语和英文词都能对上。英文仍认词，不认随便一段子串：`sorted` 不会因为出现在 `unsorted` 里就算对，`log` 也不会命中 `catalog`。评分在本地完成，不调用模型。每个主题有多道开放题，同一主题再次排进来时会换一道。当天要交的开放题会留在这组练习的最后一题。

Open answers are scored offline against the point rubric, token by token. A keyword has to stand on its own; `log` does not match inside `catalog`.

同一道题做完一轮后，下次不会立刻再抽到，除非题库用完，或者这道题到了复习日。看到的题记在 SQLite 里。

Seen items are stored in SQLite and are not served again until that pool is exhausted or the item is due for review.

## 其他命令 / Other commands

日常不需要记这些。原来的命令都还在。

```bash
interview-coach start --name Ada --role 后端
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
interview-coach research --paste
interview-coach demo
```

`research` 是可选的，做完 `today` 再想按某个岗位加重时再用。

`assess` 和 `drill` 达标时同样会自动记下当天，只要这一天的计划还没完成、练的就是这一天的主题。`drill` 只练到期主题。没有到期主题时它什么都不改，也不会重排复习日。

`drill` only practices topics that are due. If nothing is due, it leaves the schedule alone.

`demo` 会在目标数据库已存在时停下来。确认覆盖再加 `--yes`：

```bash
interview-coach demo --db data/demo.sqlite --yes
```

`--topics`、`--kinds`、`--tags` 用来缩小 `assess` 的范围。`today --kinds mcq` 或 `today --kinds open` 会改掉这一次的题型；画像里的 `--kinds` 也一样。只练一种题时，做不到的那条验收（例如只练选择题时的开放题要点）不会拿来卡你。`--answers` 的顺序必须和抽到的题目一致。

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

- **Today.** 一条命令完成「看计划 → 短练习 → 达标自动打卡 → 下一步」。没有计划会自动建。过了日期还没做的日子记为错过，连续打卡按日历断开。这一周都记完了，下一次会按完成率排下一周，并优先排已经做错的主题。
- **Assessment.** 每个主题能力值 1 到 5。答对升高，答错降低。开放题用本地 rubric 打 0 到 1 的部分分。每个主题一轮最多 6 题。题干、选项、说明和要点都是中文。
- **Exposure.** 做过的题会记下。同一题不会在下一轮立刻出现，除非这个范围内的题都见过，或者这道题到了复习日。
- **Confidence.** 信息量近似 `区分度² × p × (1 − p)`。把握度是 `信息量 / (信息量 + 1)`。这些数字还在 `progress` 里，教练开口时不拿它们当第一句话。
- **Start.** 一条命令记下每天分钟数、练习方式、自评薄弱主题，以及可选的简历或职位说明。原文不保存。它排出或刷新 7 天计划和能打分的验收标准，不编造能力分。做题记录和自评或职位说明冲突时，做题记录排前面。
- **Profile.** 一位学习者、一个职位、一个目标预设、每天分钟数。默认 30 分钟（允许 10–180）。连续打卡目标默认 5，打印出来的是已经连续完成的天数，不是把目标当成已经做到。偏好题型默认选择题加开放题。
- **Plan.** 七天。还没有做题时按权重排；出现错题之后，剩下的日子和下周会把这些主题排到前面，而不是死守一开始的字母序。收缩一周时分数线只降不升。
- **Auto-log.** `today`、`assess`、`drill` 练的是当前未完成的那一天，并且这一次实际会打分的标准都达到时，自动把这一天记为完成。分钟数是实际用时。验收里只留能打分的几条，不要求「写下 3 条定义」这种没有判分的句子。
- **Spaced review.** 练过的主题会得到 `next_review`。`due` 列出到期主题。`replan` 在 steady / stretch 时把到期主题往前排。
- **Replan.** 完成率低于 60% 则收缩。至少 85% 完成且测验正确率至少 70% 则加码。其余保持分钟数。
- **Coach.** `ask` 先说接下来约 30 分钟做什么，再给能打分的验收标准。问「我哪里弱」时只根据错题回答；还没有错题就直接说现在判断不了。
- **STAR.** 行为面试（STAR）还没做。以后可以加一个单独练习，不影响现在的每日命令。

## 布局 / Layout

```
src/interview_coach/
  assessment/   question bank, open rubrics, adaptive session, scoring, target weights
  profile/      name, job title, target preset, daily minutes, optional streak and item types
  learner/      onboarding model: habits, self-rated topics, pasted skill tags
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
