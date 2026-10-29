# 课时8：用 Skill 固化你的工作方法

> 来源：edu.aliyun.com/course/3126500/lesson/344730529

## 🚄 前言

反复用 Agent 处理同一类工作时，麻烦的不是它完全不会做，而是同样的格式、标准和例外每次都要重新说明。少说一句，输出就可能变样。

Skill 用来把这些重复说明保存成可复用的工作方法。下次遇到同类任务时，Agent 可以按这套方法执行，而不是每次临场发挥。

## ✏️ 课程目标

学完这节课后，你将能够：

- 把一套跑顺的工作方法写进 Skill。

- 调整 Skill 的触发条件和执行规则。

## 1 为什么需要 Skill：每次都要重复交代标准

先看一个周报例子。假设你每周都要让 Agent 根据工作记录整理周报，材料并不复杂：

完成客户续费名单整理，已按客户等级标注优先级。
更新“客户回访话术”说明，已放到团队共享文档。
下周客户拜访排期：3 位客户已确认时间，2 位客户待回复。
整理本周客户反馈，初步归为价格、交付和售后三类。
下周计划：跟进重点客户续费确认，补充客户反馈清单。
如果你只说：

根据这些本周工作记录，帮我整理成一份周报。
Agent 多半能写出一份周报，但每次格式可能不一样：这次叫“本周总结”，下次叫“工作进展”；这次把重点事项单独列出来，下次又散在各段正文里。

Skill 要固定的，就是这套整理方法：

- 输出结构：周报包含“本周完成 / 进行中 / 下周计划 / 待确认事项”。

- 处理规则：重要客户或紧急事项写成高优先级跟进。

- 缺失信息：材料里没有依据的内容标为“待确认”。

Skill 固化的不是某一篇周报正文，而是“周报整理”这项工作的做法。

## 2 先试用技能市场里的 Skill

知道 Skill 要固定什么之后，先去技能市场试一个别人已经整理好的 Skill。技能市场里可能已经有人把“周报怎么整理”这类方法做成了 Skill。

打开千问办公左侧的“技能”，进入“技能市场”，搜索“周报”，挑一个名称和说明都指向“写周报”或“整理进展”的 Skill。选好后，在技能详情页点击安装。安装完成后，到“用户安装”里确认它已经出现在列表里，并且开关处于打开状态。

接着用一份练习材料试一次，可以明确写出 Skill 名。例如：

请调用周报撰写 Skill，根据下面这份本周工作记录生成一份周报草稿。
试完以后，你会看到它通常能把周报整理得更像周报，但不一定完全符合你的习惯。栏目名称、重点事项写法、待确认事项放法，都可能需要调整。如果 Agent 说找不到这个 Skill，先重启 Agent 或新开会话。

## 3 把自己的周报写法保存成 Skill

试完技能市场里的 Skill 之后，你大概会发现一件事：别人整理好的方法可以帮你起步，但不一定就是你的工作方法。

如果只是差一两条规则，可以在已安装的 Skill 上补充；如果你的周报写法已经有一套固定标准，就新建一个自己的 Skill。

千问办公官方提供技能创建助手

新建 Skill 不只有一种方式。常见的有这几种，适合不同情况：

- 直接描述需求：你已经有明确的规则，比如团队 SOP 或操作手册，直接把规则告诉 Agent，让它生成 Skill。不需要先跑一遍任务。

- 给参考文件或样例：你手上有过去做得好的成品，比如几份符合标准的周报、一份格式规范的会议纪要模板，把它们交给 Agent，让它从中提炼规则并生成 Skill。

- 先跑通一次再生成：你还没想清楚规则该怎么写，先在对话里把任务做一遍、把标准调出来，再从过程中提炼成 Skill。

- 从已有 Skill 修改：安装一个技能市场或别人分享的 Skill，在它基础上改成自己的做法。

下面用周报演示"先跑通一次再生成"，因为它能完整展示一件事：怎么在还没有明确标准时，通过实际操作把规则摸清楚，再保存成 Skill。进阶实验会练习"直接描述需求"。

### 3.1 先把周报标准聊清楚

如果你还没有明确的周报标准，可以先在对话里把一次周报整理跑顺，从过程中发现规则。先让 Agent 读一份工作记录，整理出一版周报草稿。

输入这句：

请读取当前文件夹里的本周工作记录、会议纪要和已有周报样例，先总结我常用的周报栏目和写法，再整理一份本周周报草稿。没有依据的信息不要猜，标为“待确认”。
看完第一版之后，不要急着创建 Skill。先把不符合你标准的地方改出来。例如可以继续说：

周报请固定分成“本周完成 / 进行中 / 下周计划 / 待确认事项”。
“2 位客户待回复”不能写成已完成，请放到待确认事项。
“整理客户反馈”如果材料里没有写完成结论，请放到进行中。
每周都按这个栏目顺序输出，不要临时改栏目名。
这一步的目的不是只得到一份更好的周报，而是把“从哪里找材料、事项怎么分栏、按什么格式输出”的流程说清楚。等你发现“这样做才对”，这些来回沟通就可以变成 Skill 的素材。

### 3.2 根据沟通记录创建 Skill

到这里，周报的栏目、分栏规则和输出顺序已经清楚了。接下来要做的，是让创建助手把这些规则整理成 Skill 文件。千问办公内置了创建 Skill 的能力，本课统一把这类辅助能力叫 create-skill。有些工具或资料也会把类似能力叫 skill-creator。这个能力会按照 Skill 的固定文件结构和写法要求生成初稿。

这套周报规则只服务于当前练习项目，所以这次把它保存到当前项目里，也就是创建一个项目级 Skill。这样下次在这个项目里写周报时，Agent 就能继续按这套做法处理。

根据刚才整理和修改周报的过程，帮我创建一个当前项目使用的“周报整理”Skill。
生成后，让 Agent 告诉你这个 Skill 保存在哪里。先不用细看文件内容，下一步先用一条周报请求确认它能不能被调用。

### 3.3 测试确认 Skill 能否被调用

创建完后，先别急着研究文件内容。先问一个简单问题：Agent 能不能找到这个 Skill，并按里面的做法写周报。

可以明确写出 Skill 名：

请使用周报整理 Skill，读取当前文件夹里的“本周工作记录”和“会议纪要”，生成一份周报草稿。
这次测试不追求一份完美周报。先看它有没有按固定几部分写，待确认事项有没有单独列出来，缺少依据的内容有没有标成“待确认”。

## 4 看懂 Skill 和提示词模板有什么不同

生成并调用过一次之后，再看 Skill 的结构会更容易理解。你可能会觉得：这不就是把一段提示词存起来吗？

差别在于，提示词模板需要你每次复制到对话里；Skill 会先用一小段说明让 Agent 判断这次要不要用它，确认要用以后，再读取完整做法。

Skill 在电脑里通常是一个文件夹，例如 weekly-report-draft。里面的核心文件是一份 SKILL.md。打开它，先看两块就够了：

- 开头的name和description：告诉 Agent 这个 Skill 叫什么、什么时候该用。

- 正文：写完整做法，比如先读哪些材料、周报包含哪些部分、待确认事项怎么写、缺少依据时怎么处理。

这里要注意 description 的作用。Agent 启动时，只会读取每个 Skill 的 name 和 description，不会读正文。它靠这一小段话来判断"这次任务要不要用这个 Skill"。判断要用以后，才去读完整的正文。

所以 description 是 Agent 选择 Skill 的依据。写得不准，Agent 就找不到它；写得太模糊，几个 Skill 之间就容易选错。

Skill 文件夹里也常见 references/、scripts/ 等子目录。references/ 可以放模板、术语表、案例说明，scripts/ 可以放自动检查脚本。

这些内容也不是一次性全塞给 Agent。需要模板或脚本时，才继续读取 references/ 或 scripts/。

这种按需读取的方式，也叫渐进式披露。它的好处是：不用每轮对话都塞进一大段规则，但 Agent 真要处理这类任务时，又能拿到完整做法。看懂这个结构后，调用出问题时就知道该改哪一处。

## 5 把调用中发现的问题补回 Skill

### 5.1 没有自动调用，就改描述

Skill 能被调用，不代表它已经好用。调用后先看一件事：Agent 是不是主动用了这个 Skill。

如果你只是说“帮我整理本周进展”，Agent 没有使用周报整理 Skill，问题通常不在周报规则，而在开头那段触发说明。

这段说明要写出你平时真的会说的话，比如：

当用户说”帮我写周报””整理本周进展””根据工作记录生成周报”时，使用这个 Skill。
如果只写”用于结构化工作汇报生成”，看起来正式，但 Agent 不一定容易判断什么时候该用。

写 description 时还有几个常见问题：

- 用了第一人称。description 会被注入到 Agent 的系统提示里，写”我可以帮你整理周报”会让 Agent 困惑这段话是谁说的。应该写成”根据工作记录整理周报”这样的第三人称陈述。

- 关键词没有放在前面。某些 Agent 对 description 有字符数上限，超出部分会被截断。所以最重要的触发词要写在开头，例如先写”整理周报、生成本周进展”，再写补充说明。

- 把具体规则写进了 description。前面讲过，Agent 启动时会读取所有 Skill 的 description，但只有决定使用某个 Skill 以后才会读它的正文。description 里只需要写”这个 Skill 做什么、什么时候触发”，让 Agent 能判断该不该用就够了。具体的栏目、规则、输出格式放在正文里——它们是 Agent 确定要用这个 Skill 以后才需要知道的。把规则也塞进 description，只会占用每轮对话都要消耗的上下文空间，但对触发判断没有帮助。

下面用周报和会议纪要两个场景，对比看 description 怎样写更容易被 Agent 找到：

写法

description

问题

不推荐

用于结构化工作汇报生成

太抽象，Agent 难以判断什么时候该用

不推荐

我可以帮你整理周报

第一人称，注入系统提示后容易混淆

推荐

根据工作记录整理周报。当用户说”帮我写周报””整理本周进展””根据工作记录生成周报”时使用

第三人称，关键词在前，触发场景明确

推荐

根据会议记录生成 Word 会议纪要。当用户说”整理会议纪要””写会议记录”时使用

同上，换了一个场景

### 5.2 调用了但结果不对，就把问题写回 Skill

如果 Agent 已经使用了这个 Skill，但生成的周报还是不符合你的习惯，不要只改这一次周报。

比如它把待回复、待确认的事项散在正文里，没有单独列出“待确认事项”。你当然可以让它把这份周报改对，但真正有用的是让 Agent 把“待确认事项要单独列出”补回 Skill。这样下次再遇到类似材料，它才知道该怎么处理。

### 5.3 规则不要只针对这一次

补规则时，不要写成“这次客户续费名单要写高优先级”。这句话只管这一次材料。

更好的写法是：

重要客户、临近截止时间、影响交付的事项，写成高优先级跟进。
这条规则去掉了“客户续费名单”这个只属于本次材料的细节，保留了下次还能用的判断方法。

改完以后，还要换样本验证。不要只拿刚才那份周报反复测，否则你不知道 Skill 是真的记住了规则，还是只修好了这一个例子。

### 5.4 换样本验证 Skill

换样本时，可以准备 2 到 3 份差异明显的材料：一份信息完整，一份缺负责人或截止时间，一份包含待确认或冲突信息。每次调用后看三件事：是否触发了这个 Skill，是否按固定结构输出，是否把缺失和不确定内容标出来。

如果这个 Skill 会被团队反复使用，可以把测试样本再扩大一些，记录常见失败原因：触发不准、栏目跑偏、待确认漏掉、脚本检查失败。下一轮修改时，不是只修某一次输出，而是把失败原因补回触发说明、执行规则、参考资料或脚本。

## 6 换到别的任务时，也这样找和用 Skill

周报只是一次练习。换成页面、数据分析、读书笔记时，判断方式不变：先看技能市场或别人分享的 Skill 里有没有合适的，试一次；如果只差几条规则，就在已安装的 Skill 上补充；如果你的做法已经比较固定，再新建自己的 Skill。

### 6.1 按任务关键词找 Skill

下次遇到新任务，先从技能市场找。比如你要让 Agent 做产品介绍页，可以打开千问办公左侧的“技能”，进入技能市场，搜索“前端设计”“SEO”或“页面设计”。挑一个说明清楚、场景对得上的 Skill，安装后用一个练习任务试一次。

如果不确定该搜什么关键词，也可以直接让 Agent 帮你找：

帮我在技能市场找一个适合做产品介绍页的 Skill。
千问办公会在背后调用 find-skills 这类查找技能，到技能市场里搜索并返回候选结果。

技能市场里找不到合适的，再看公开 Skills 市场或 GitHub 开源仓库：

https://agentskill.sh

https://skillsmp.com

https://officialskills.sh

在 GitHub 里，可以搜索 agent skills、SKILL.md、Claude Skills 这类关键词。

### 6.2 让 Agent 帮你安装

找到 Skill 后，先确认来源，再安装。在千问办公技能市场里，通常可以在技能详情页直接点击安装。

如果你拿到了别人分享的 Skill 安装命令，可以直接发给千问办公：

请帮我安装这个 Skill：npx skills add vercel-labs/agent-skills --skill frontend-design
如果你拿到的是 Skill 页面链接，也可以直接发给千问办公：

帮我安装这个 Skill：https://qoder.com/marketplace/xxx
千问办公会尝试识别命令或链接、下载对应文件夹，并把它放到合适的位置。

安装过程中，如果千问办公问你“安装到用户级还是项目级”，可以按下面的规则选：

安装位置

适合放什么

例子

用户级 Skill

个人在多个项目中复用的方法

个人写作风格、常用汇报格式、PPT 偏好

项目级 Skill

当前项目或团队共享的方法

客户反馈规范、课程文档写作规范、团队复盘模板

简单判断：

- 只服务于个人习惯，并且多个项目都会用到，选用户级。

- 和当前项目强相关，或者希望团队按同一标准使用，选项目级。

个人 Skill 用来保存自己的写作习惯和常用格式；团队 Skill 用来让多人按同一套标准处理工作；组织或产品负责人维护的 Skill，则适合承载更成熟、需要持续更新的流程。

这个选择不是一次性决定。以后如果发现放错了范围，通常可以再让 Agent 帮你调整，例如“把这个 Skill 从项目级改成用户级”。

### 6.3 创建和修改 Skill 时的自查清单

为了减少找不到、误触发和选错 Skill，创建或修改时可以从三方面自查。

数量和触发

- Skill 不是越多越好：每个 Skill 的 name 和 description 都会占用上下文；装得太多，Agent 要看的说明变长，名字和触发条件接近时也更容易选错。

正文内容

- 少写常识，多写判断标准：不要解释 PDF、周报、会议纪要这类 Agent 已经知道的概念，优先写你的栏目、处理规则、例外情况和检查方式。

- 不要只写人设，要写清步骤：提示词里可以用角色帮助 Agent 理解任务风格，但 Skill 不能只写“你是一位资深专家”。更有用的是写清动作，比如“先读取材料，再按这几个栏目输出；缺少依据的内容标为待确认”。

- 写当前做法：默认写现在应该怎么做；废弃做法可以单独说明，不要让 Agent 在一堆日期条件里判断该用哪套规则。

文件组织和任务拆分

- SKILL.md只放主要做法：正文里写任务流程、输出格式、判断标准和异常处理；长模板、案例、术语表放到 references/；复杂检查可以放到 scripts/。判断标准是：SKILL.md 正文一旦被 Agent 加载，就会在整个会话中保持在上下文里。每次执行都要用到的核心流程放正文；只在特定情况下才需要的详细参考放单独文件，Agent 会在需要时再去读取。一般建议 SKILL.md 正文不超过 500 行，接近这个长度时就考虑把部分内容拆到单独文件里。

- 开放任务用文字，精确任务用脚本：写作、审稿、资料整理这类任务，适合用文字说明判断标准；文件批量重命名、表格校验、格式检查这类任务，适合沉淀成脚本。

- 复杂任务可以组合多个 Skill：当一个任务自然分成“收集材料、生成初稿、检查质量、整理发布”等不同环节时，可以让不同 Skill 各负责一段。组合时要写清每个 Skill 的输入、输出和交接结果，例如先用资料整理 Skill 提取事实，再用写作 Skill 生成草稿，最后用检查 Skill 看格式和遗漏。不要为了显得完整而把一个简单流程拆成很多 Skill；如果只是同一类任务里的几个固定步骤，优先放在同一个 Skill 里。

### 6.4 Skill 管方法，MCP 管能力

最后别把 Skill 和工具混在一起。Skill 解决的是“这类工作应该怎么做”。比如写周报时，固定栏目、事项归类、待确认事项怎么写，这些都适合写进 Skill。

MCP 或外部工具解决的是“Agent 能不能拿到资料、能不能执行动作”。比如读取业务系统、查数据、操作文档、调用服务，这些靠工具能力完成。

同一个任务里，两者可以一起用。比如做客户拜访准备时，Skill 可以规定：先用企业客户系统 MCP 读取客户最近沟通记录，再用日历 MCP 查可约时间，最后用高德地图 MCP 估算路程，并按“客户背景 / 近期问题 / 拜访时间 / 路线安排”输出。

## 动手实验：安装并试用一个别人分享的 Skill

周报演示之后，这个实验换一个场景，练习从查找、安装、试用到决定是否保留的完整流程。建议在新会话或临时项目里做，避免影响当前练习环境。

- 从千问办公技能市场、公开 Skills 市场或 GitHub 找一个说明清楚的 Skill。可以选择“读书笔记整理”“Notion 信息图”“前端设计”这类和周报不同的任务。

- 安装前先看它适合什么场景、是否需要读取本地文件、是否会运行脚本、来源页面是否清楚。

- 让千问办公帮你安装；如果提示确认命令、目录或权限，先看清楚再同意。

- 用一个低风险练习任务明确调用它，观察 Agent 是否能找到并使用。

- 如果效果有用，再决定保留；如果频繁误触发、说明模糊或来源不可信，就不要长期使用。

你需要观察并思考：

- 这个 Skill 适合处理哪类任务？

- 它有没有减少你重复交代标准的次数？

- 它有哪些地方不符合你的习惯？

- 你会保留它、调整它，还是删除它？

## 进阶实验：用已有规则直接创建一个会议纪要整理 Skill

上一个实验只试用别人分享的 Skill。这个进阶实验换一个不同的创建方式：你已经知道会议纪要该怎么写，直接把规则告诉 Agent，让它生成 Skill。

周报演示走的是”先跑通再生成”的路径，适合标准还没想清楚的情况。这次反过来：假设你的团队已经有一套固定的会议纪要标准，直接描述需求来创建 Skill。开始前，先在千问办公中选择当前练习项目作为工作目录。

- 直接把你的会议纪要标准告诉 Agent，让它创建 Skill。可以输入：

帮我创建一个项目级”会议纪要整理”Skill，默认生成 Word 会议纪要。规则如下：
- 固定包含”会议结论 / 待办事项 / 下次跟进 / 待确认事项”四个栏目。
- 每条待办事项必须写明负责人和截止时间；如果会议记录里没有，标为”待确认”。
- 没有明确结论的讨论事项，放到”下次跟进”而不是”会议结论”。
- 请说明 Skill 放在哪里，以及 description 是怎样写的。

- 生成后检查 SKILL.md。项目级 Skill 通常位于当前工作目录的 skills/{skill-name}/SKILL.md。重点看：是否默认生成 Word、是否固定四个栏目、是否说明负责人、截止时间和待确认事项的处理规则。

- 用下面这段练习材料测试一次，明确调用这个 Skill：

会议记录：
1. 下周三前，运营同学补充活动页文案初稿，负责人：李青。
2. 客服反馈整理表需要增加”问题类型”和”是否影响续费”两列，负责人待确认。
3. 新版首页发布时间暂定 5 月 28 日，但还要等相关同学确认隐私声明。
4. 产品介绍页的首屏文案已经定稿。
5. 下次会议前，需要汇总活动页文案、客服反馈表和首页发布时间三件事的进展。
请使用会议纪要整理 Skill，根据上面的会议记录生成一份 Word 会议纪要，文件名为”会议纪要练习.docx”。

- 检查生成的 Word 内容，看栏目、负责人、截止时间和待确认事项是否符合你写进 Skill 的规则。

- 换一份会议记录再调用一次，确认输出是否稳定。

- 如果发现规则写得不够细或遗漏了某些情况，把问题更新到 Skill 对应位置，例如触发说明、执行规则、参考资料或脚本，再调用一次。

本实验的预期结果不是让 Agent 两次输出完全一样，而是让它在调用会议纪要整理 Skill 时，稳定按你的栏目和判断标准生成 Word 会议纪要。和周报实验对比，你会发现：当规则已经明确时，直接描述需求创建 Skill 比先跑通一次任务更快。

## ✅ 本节小结

Skill 的价值，不是把提示词换个地方保存，而是把一类重复任务的触发条件、执行步骤、输出格式和异常处理规则沉淀下来，让 Agent 下次按同一套方法处理。

如果周报、会议纪要、资料整理这类任务以后还会反复出现，可以先从技能市场或别人分享的 Skill 里找一个试用；不合适时，再新建自己的 Skill。标准已经明确的，直接描述需求让 Agent 生成；标准还没想清楚的，先在对话里把任务跑顺再提炼。创建后换一份材料测试，把发现的问题更新到对应位置，例如触发说明、执行规则、参考资料或脚本。

## ✅ 评价反馈

欢迎你参与阿里云大模型ACA课程调查问卷反馈学习体验和课程评价。

你的批评和鼓励都是我们前进的动力！

eyJ2IjoxLCJqdGkiOiI3MWMyYTYxMDIzYTg0MzdhYWVhYTBlYWY1YWY0MzBkMSIsImxpZCI6MzQ0NzMwNTI5LCJjaWQiOjMxMjY1MDAsInVpZCI6MTQ3MzUzNjI0MjM2MTM2NywiZXhwIjoxNzkxNzM2MTAxfQ.4vSlqJ9nbmTbLTUTi1keZ14C0UEUlDpCjVCWrzmq7j0

["root", {}, ["h2", {"uuid": "mar4ljfqhs1snlzwcrnv", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "🚄 前言"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "97cnya"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "反复用 Agent 处理同一类工作时，麻烦的不是它完全不会做，而是同样的格式、标准和例外每次都要重新说明。少说一句，输出就可能变样。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "Skill 用来把这些重复说明保存成可复用的工作方法。下次遇到同类任务时，Agent 可以按这套方法执行，而不是每次临场发挥。"]]], ["h2", {"uuid": "tu8ufduroh9vykt8b9j7", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "✏️ 课程目标"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "mzdh8a"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "学完这节课后，你将能够："]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "4k2rk22ij69m", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "把一套跑顺的工作方法写进 Skill。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "4k2rk22ij69m", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "调整 Skill 的触发条件和执行规则。"]]], ["h2", {"uuid": "u62kntb7fsy4xzhaajy8", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "1 为什么需要 Skill：每次都要重复交代标准"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "6pfuvk"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "先看一个周报例子。假设你每周都要让 Agent 根据工作记录整理周报，材料并不复杂："]]], ["code", {"uuid": "wdke81yv0xohyf3n2l1y", "language": "text-x-markdown"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "完成客户续费名单整理，已按客户等级标注优先级。\n更新“客户回访话术”说明，已放到团队共享文档。\n下周客户拜访排期：3 位客户已确认时间，2 位客户待回复。\n整理本周客户反馈，初步归为价格、交付和售后三类。\n下周计划：跟进重点客户续费确认，补充客户反馈清单。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "如果你只说："]]], ["code", {"uuid": "nsszqd9w3bc5muten0kt", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "根据这些本周工作记录，帮我整理成一份周报。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "Agent 多半能写出一份周报，但每次格式可能不一样：这次叫“本周总结”，下次叫“工作进展”；这次把重点事项单独列出来，下次又散在各段正文里。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["img", {"id": "szc74o", "src": "https://scms-prod-sh-public.oss-cn-shanghai.aliyuncs.com/course_picture/fhtmgqaxbwwuopkpwmfn.svg", "width": 800, "height": 449}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "Skill 要固定的，就是这套整理方法："]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "m6acnw22j26n", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "输出结构：周报包含“本周完成 / 进行中 / 下周计划 / 待确认事项”。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "m6acnw22j26n", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "处理规则：重要客户或紧急事项写成高优先级跟进。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "m6acnw22j26n", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "缺失信息：材料里没有依据的内容标为“待确认”。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "Skill 固化的不是某一篇周报正文，而是“周报整理”这项工作的做法。"]]], ["h2", {"uuid": "x94xdzr8dvwabxgh7zsw", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "2 先试用技能市场里的 Skill"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "lfi6hl"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "知道 Skill 要固定什么之后，先去技能市场试一个别人已经整理好的 Skill。技能市场里可能已经有人把“周报怎么整理”这类方法做成了 Skill。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["img", {"id": "jda9ju", "src": "https://img.alicdn.com/imgextra/i1/O1CN01YC7Ovl1wvW5xjnwHB_!!6000000006370-0-tps-1750-942.jpg", "width": 826, "height": 396}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "打开千问办公左侧的“技能”，进入“技能市场”，搜索“周报”，挑一个名称和说明都指向“写周报”或“整理进展”的 Skill。选好后，在技能详情页点击安装。安装完成后，到“用户安装”里确认它已经出现在列表里，并且开关处于打开状态。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "接着用一份练习材料试一次，可以明确写出 Skill 名。例如："]]], ["code", {"uuid": "1z0oj1eb27c9bmvv6tqc", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "请调用周报撰写 Skill，根据下面这份本周工作记录生成一份周报草稿。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "试完以后，你会看到它通常能把周报整理得更像周报，但不一定完全符合你的习惯。栏目名称、重点事项写法、待确认事项放法，都可能需要调整。如果 Agent 说找不到这个 Skill，先重启 Agent 或新开会话。"]]], ["h2", {"uuid": "jizj27ko0n4a86ak30eh", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "3 把自己的周报写法保存成 Skill"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "cstc89"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "试完技能市场里的 Skill 之后，你大概会发现一件事：别人整理好的方法可以帮你起步，但不一定就是你的工作方法。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "如果只是差一两条规则，可以在已安装的 Skill 上补充；如果你的周报写法已经有一套固定标准，就新建一个自己的 Skill。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["img", {"id": "f6oxk4", "src": "https://img.alicdn.com/imgextra/i2/O1CN01JdIMjR8lVrH31JSi_!!6000000001255-0-tps-1488-664.jpg", "width": 582, "height": 192}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "千问办公官方提供技能创建助手"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "新建 Skill 不只有一种方式。常见的有这几种，适合不同情况："]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "vqwzpya5h9nw", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "直接描述需求"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "：你已经有明确的规则，比如团队 SOP 或操作手册，直接把规则告诉 Agent，让它生成 Skill。不需要先跑一遍任务。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "vqwzpya5h9nw", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "给参考文件或样例"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "：你手上有过去做得好的成品，比如几份符合标准的周报、一份格式规范的会议纪要模板，把它们交给 Agent，让它从中提炼规则并生成 Skill。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "vqwzpya5h9nw", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "先跑通一次再生成"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "：你还没想清楚规则该怎么写，先在对话里把任务做一遍、把标准调出来，再从过程中提炼成 Skill。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "vqwzpya5h9nw", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "从已有 Skill 修改"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "：安装一个技能市场或别人分享的 Skill，在它基础上改成自己的做法。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "下面用周报演示\"先跑通一次再生成\"，因为它能完整展示一件事：怎么在还没有明确标准时，通过实际操作把规则摸清楚，再保存成 Skill。进阶实验会练习\"直接描述需求\"。"]]], ["h3", {"uuid": "bi00eki1lxlpdiun6hhv"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "3.1 先把周报标准聊清楚"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "如果你还没有明确的周报标准，可以先在对话里把一次周报整理跑顺，从过程中发现规则。先让 Agent 读一份工作记录，整理出一版周报草稿。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "输入这句："]]], ["code", {"uuid": "fmx6s6k8j3vgbxeovt24", "language": "text-x-markdown"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "请读取当前文件夹里的本周工作记录、会议纪要和已有周报样例，先总结我常用的周报栏目和写法，再整理一份本周周报草稿。没有依据的信息不要猜，标为“待确认”。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "看完第一版之后，不要急着创建 Skill。先把不符合你标准的地方改出来。例如可以继续说："]]], ["code", {"uuid": "2qyj8h8vt2tw60qdp229", "language": "text-x-markdown"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "周报请固定分成“本周完成 / 进行中 / 下周计划 / 待确认事项”。\n“2 位客户待回复”不能写成已完成，请放到待确认事项。\n“整理客户反馈”如果材料里没有写完成结论，请放到进行中。\n每周都按这个栏目顺序输出，不要临时改栏目名。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "这一步的目的不是只得到一份更好的周报，而是把“从哪里找材料、事项怎么分栏、按什么格式输出”的流程说清楚。等你发现“这样做才对”，这些来回沟通就可以变成 Skill 的素材。"]]], ["h3", {"uuid": "qd6f5tsqqsqmngrdura1"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "3.2 根据沟通记录创建 Skill"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "到这里，周报的栏目、分栏规则和输出顺序已经清楚了。接下来要做的，是让创建助手把这些规则整理成 Skill 文件。千问办公内置了创建 Skill 的能力，本课统一把这类辅助能力叫 "]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "create-skill"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "。有些工具或资料也会把类似能力叫 "]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "skill-creator"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "。这个能力会按照 Skill 的固定文件结构和写法要求生成初稿。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "这套周报规则只服务于当前练习项目，所以这次把它保存到当前项目里，也就是创建一个项目级 Skill。这样下次在这个项目里写周报时，Agent 就能继续按这套做法处理。"]]], ["code", {"uuid": "yimxkwivc1kvptc8fimy", "language": "text-x-markdown"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "根据刚才整理和修改周报的过程，帮我创建一个当前项目使用的“周报整理”Skill。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "生成后，让 Agent 告诉你这个 Skill 保存在哪里。先不用细看文件内容，下一步先用一条周报请求确认它能不能被调用。"]]], ["h3", {"uuid": "eiddip30po01u7kmwpb9"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "3.3 测试确认 Skill 能否被调用"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "创建完后，先别急着研究文件内容。先问一个简单问题：Agent 能不能找到这个 Skill，并按里面的做法写周报。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "可以明确写出 Skill 名："]]], ["code", {"uuid": "q32wdbcn1jasq2wrcgy9", "language": "text-x-markdown"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "请使用周报整理 Skill，读取当前文件夹里的“本周工作记录”和“会议纪要”，生成一份周报草稿。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "这次测试不追求一份完美周报。先看它有没有按固定几部分写，待确认事项有没有单独列出来，缺少依据的内容有没有标成“待确认”。"]]], ["h2", {"uuid": "0moehg4esydzzune7x8l", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "4 看懂 Skill 和提示词模板有什么不同"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "生成并调用过一次之后，再看 Skill 的结构会更容易理解。你可能会觉得：这不就是把一段提示词存起来吗？"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "差别在于，提示词模板需要你每次复制到对话里；Skill 会先用一小段说明让 Agent 判断这次要不要用它，确认要用以后，再读取完整做法。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "Skill 在电脑里通常是一个文件夹，例如 "]], ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "weekly-report-draft"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "。里面的核心文件是一份 "]], ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "SKILL.md"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "。打开它，先看两块就够了："]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "7zjqx868vmy8", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "开头的"]], ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "name"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "和"]], ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "description"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "：告诉 Agent 这个 Skill 叫什么、什么时候该用。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "7zjqx868vmy8", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "正文"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "：写完整做法，比如先读哪些材料、周报包含哪些部分、待确认事项怎么写、缺少依据时怎么处理。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "这里要注意 "]], ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "description"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, " 的作用。Agent 启动时，只会读取每个 Skill 的 "]], ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "name"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, " 和 "]], ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "description"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "，不会读正文。它靠这一小段话来判断\"这次任务要不要用这个 Skill\"。判断要用以后，才去读完整的正文。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "所以 "]], ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "description"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, " 是 Agent 选择 Skill 的依据。写得不准，Agent 就找不到它；写得太模糊，几个 Skill 之间就容易选错。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "Skill 文件夹里也常见 "]], ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "references/"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "、"]], ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "scripts/"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, " 等子目录。"]], ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "references/"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, " 可以放模板、术语表、案例说明，"]], ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "scripts/"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, " 可以放自动检查脚本。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "这些内容也不是一次性全塞给 Agent。需要模板或脚本时，才继续读取 "]], ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "references/"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, " 或 "]], ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "scripts/"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["img", {"id": "pch5zt", "src": "https://scms-prod-sh-public.oss-cn-shanghai.aliyuncs.com/course_picture/hgyqrsmlscltrtavppgy.svg", "width": 800, "height": 352}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "这种按需读取的方式，也叫渐进式披露。它的好处是：不用每轮对话都塞进一大段规则，但 Agent 真要处理这类任务时，又能拿到完整做法。看懂这个结构后，调用出问题时就知道该改哪一处。"]]], ["h2", {"uuid": "2yegmms95c7k6pefa8tn", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "5 把调用中发现的问题补回 Skill"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "tisn99"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["h3", {"uuid": "2tdju505lyjvrczl4xxs"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "5.1 没有自动调用，就改描述"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "Skill 能被调用，不代表它已经好用。调用后先看一件事：Agent 是不是主动用了这个 Skill。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "如果你只是说“帮我整理本周进展”，Agent 没有使用周报整理 Skill，问题通常不在周报规则，而在开头那段触发说明。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "这段说明要写出你平时真的会说的话，比如："]]], ["code", {"uuid": "7my8lpcxqizub7wai7k7", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "当用户说”帮我写周报””整理本周进展””根据工作记录生成周报”时，使用这个 Skill。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "如果只写”用于结构化工作汇报生成”，看起来正式，但 Agent 不一定容易判断什么时候该用。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "写 description 时还有几个常见问题："]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "1t3mn09wqpgq", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "用了第一人称"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "。description 会被注入到 Agent 的系统提示里，写”我可以帮你整理周报”会让 Agent 困惑这段话是谁说的。应该写成”根据工作记录整理周报”这样的第三人称陈述。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "1t3mn09wqpgq", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "关键词没有放在前面"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "。某些 Agent 对 description 有字符数上限，超出部分会被截断。所以最重要的触发词要写在开头，例如先写”整理周报、生成本周进展”，再写补充说明。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "1t3mn09wqpgq", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "把具体规则写进了 description"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "。前面讲过，Agent 启动时会读取所有 Skill 的 description，但只有决定使用某个 Skill 以后才会读它的正文。description 里只需要写”这个 Skill 做什么、什么时候触发”，让 Agent 能判断该不该用就够了。具体的栏目、规则、输出格式放在正文里——它们是 Agent 确定要用这个 Skill 以后才需要知道的。把规则也塞进 description，只会占用每轮对话都要消耗的上下文空间，但对触发判断没有帮助。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "下面用周报和会议纪要两个场景，对比看 description 怎样写更容易被 Agent 找到："]]], ["table", {"sr": true, "colsWidth": [244, 244, 244], "uuid": "m0k7vnqr1r4v1e1uomtb"}, ["tr", {"uuid": "3s29pk33zy45ccirieej", "h": 0}, ["tc", {"vAlign": "top", "uuid": "tkfznnkno9mde9vh0r3g", "hidden": false, "rowSpan": 1, "colSpan": 1}, ["p", {}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "写法"]]]], ["tc", {"vAlign": "top", "uuid": "5z5oc229mhc5lk1s8vqp", "hidden": false, "rowSpan": 1, "colSpan": 1}, ["p", {}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "description"]]]], ["tc", {"vAlign": "top", "uuid": "mp6zqcdpuf3z3ijzyv0x", "hidden": false, "rowSpan": 1, "colSpan": 1}, ["p", {}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "问题"]]]]], ["tr", {"uuid": "kx99klwc0rrzru63f5qh", "h": 0}, ["tc", {"vAlign": "top", "uuid": "fnwe1l1c1rsr752e2bvf", "hidden": false, "rowSpan": 1, "colSpan": 1}, ["p", {}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "不推荐"]]]], ["tc", {"vAlign": "top", "uuid": "drv722n9d0ahhm33z8sb", "hidden": false, "rowSpan": 1, "colSpan": 1}, ["p", {}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "用于结构化工作汇报生成"]]]], ["tc", {"vAlign": "top", "uuid": "80lswx4jr0uvrlgs9zfd", "hidden": false, "rowSpan": 1, "colSpan": 1}, ["p", {}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "太抽象，Agent 难以判断什么时候该用"]]]]], ["tr", {"uuid": "blnthqg138784800domj", "h": 0}, ["tc", {"vAlign": "top", "uuid": "v12lpxm1vzs1leb39dkn", "hidden": false, "rowSpan": 1, "colSpan": 1}, ["p", {}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "不推荐"]]]], ["tc", {"vAlign": "top", "uuid": "eaagpeaultgf927281h8", "hidden": false, "rowSpan": 1, "colSpan": 1}, ["p", {}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "我可以帮你整理周报"]]]], ["tc", {"vAlign": "top", "uuid": "zyg5hkpx5nxtrlfazui2", "hidden": false, "rowSpan": 1, "colSpan": 1}, ["p", {}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "第一人称，注入系统提示后容易混淆"]]]]], ["tr", {"uuid": "583a3soh67dvxjr3vpx5", "h": 0}, ["tc", {"vAlign": "top", "uuid": "5d9l2m4kzta7zv3p0pmv", "hidden": false, "rowSpan": 1, "colSpan": 1}, ["p", {}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "推荐"]]]], ["tc", {"vAlign": "top", "uuid": "txcp2cjeoxr41dtf8tbt", "hidden": false, "rowSpan": 1, "colSpan": 1}, ["p", {}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "根据工作记录整理周报。当用户说”帮我写周报””整理本周进展””根据工作记录生成周报”时使用"]]]], ["tc", {"vAlign": "top", "uuid": "ry8s6wul4ii47li18vch", "hidden": false, "rowSpan": 1, "colSpan": 1}, ["p", {}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "第三人称，关键词在前，触发场景明确"]]]]], ["tr", {"uuid": "bxsa7dsptsv5fzaazwqm", "h": 0}, ["tc", {"vAlign": "top", "uuid": "m737n3ozs66wxvu2j5m9", "hidden": false, "rowSpan": 1, "colSpan": 1}, ["p", {}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "推荐"]]]], ["tc", {"vAlign": "top", "uuid": "f1h1myz2hsb0f8fshn1s", "hidden": false, "rowSpan": 1, "colSpan": 1}, ["p", {}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "根据会议记录生成 Word 会议纪要。当用户说”整理会议纪要””写会议记录”时使用"]]]], ["tc", {"vAlign": "top", "uuid": "6k38yjcdfou2brwum2ms", "hidden": false, "rowSpan": 1, "colSpan": 1}, ["p", {}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "同上，换了一个场景"]]]]]], ["h3", {"uuid": "uah3w5sm0ncjin2asp0i"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "5.2 调用了但结果不对，就把问题写回 Skill"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "如果 Agent 已经使用了这个 Skill，但生成的周报还是不符合你的习惯，不要只改这一次周报。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "比如它把待回复、待确认的事项散在正文里，没有单独列出“待确认事项”。你当然可以让它把这份周报改对，但真正有用的是让 Agent 把“待确认事项要单独列出”补回 Skill。这样下次再遇到类似材料，它才知道该怎么处理。"]]], ["h3", {"uuid": "z3plglehpa5a976qou1p"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "5.3 规则不要只针对这一次"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "补规则时，不要写成“这次客户续费名单要写高优先级”。这句话只管这一次材料。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "更好的写法是："]]], ["code", {"uuid": "4k4d9ydl5r1ro8zn4w3t", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "重要客户、临近截止时间、影响交付的事项，写成高优先级跟进。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "这条规则去掉了“客户续费名单”这个只属于本次材料的细节，保留了下次还能用的判断方法。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "改完以后，还要换样本验证。不要只拿刚才那份周报反复测，否则你不知道 Skill 是真的记住了规则，还是只修好了这一个例子。"]]], ["h3", {"uuid": "hwj8za5qcanji097iucc"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "5.4 换样本验证 Skill"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "换样本时，可以准备 2 到 3 份差异明显的材料：一份信息完整，一份缺负责人或截止时间，一份包含待确认或冲突信息。每次调用后看三件事：是否触发了这个 Skill，是否按固定结构输出，是否把缺失和不确定内容标出来。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "如果这个 Skill 会被团队反复使用，可以把测试样本再扩大一些，记录常见失败原因：触发不准、栏目跑偏、待确认漏掉、脚本检查失败。下一轮修改时，不是只修某一次输出，而是把失败原因补回触发说明、执行规则、参考资料或脚本。"]]], ["h2", {"uuid": "fkx3biskjxyxxb1lhb8f", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "6 换到别的任务时，也这样找和用 Skill"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "nxz3zy"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "周报只是一次练习。换成页面、数据分析、读书笔记时，判断方式不变：先看技能市场或别人分享的 Skill 里有没有合适的，试一次；如果只差几条规则，就在已安装的 Skill 上补充；如果你的做法已经比较固定，再新建自己的 Skill。"]]], ["h3", {"uuid": "6gv99sz3b774csaa86gm"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "6.1 按任务关键词找 Skill"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "下次遇到新任务，先从技能市场找。比如你要让 Agent 做产品介绍页，可以打开千问办公左侧的“技能”，进入技能市场，搜索“前端设计”“SEO”或“页面设计”。挑一个说明清楚、场景对得上的 Skill，安装后用一个练习任务试一次。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "如果不确定该搜什么关键词，也可以直接让 Agent 帮你找："]]], ["code", {"uuid": "kvptzdgml6lztau43qdg", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "帮我在技能市场找一个适合做产品介绍页的 Skill。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "千问办公会在背后调用 "]], ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "find-skills"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, " 这类查找技能，到技能市场里搜索并返回候选结果。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "技能市场里找不到合适的，再看公开 Skills 市场或 GitHub 开源仓库："]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}, "blockquote": true}, ["a", {"href": "https://agentskill.sh"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "https://agentskill.sh"]]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}, "blockquote": true}, ["a", {"href": "https://skillsmp.com"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "https://skillsmp.com"]]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}, "blockquote": true}, ["a", {"href": "https://officialskills.sh"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "https://officialskills.sh"]]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "在 GitHub 里，可以搜索 "]], ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "agent skills"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "、"]], ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "SKILL.md"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "、"]], ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "Claude Skills"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, " 这类关键词。"]]], ["h3", {"uuid": "o6ymj61c1nkal3w93g0n"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "6.2 让 Agent 帮你安装"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "找到 Skill 后，先确认来源，再安装。在千问办公技能市场里，通常可以在技能详情页直接点击安装。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "如果你拿到了别人分享的 Skill 安装命令，可以直接发给千问办公："]]], ["code", {"uuid": "uyctzooo56thjkupynh2", "language": "text-x-markdown"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "请帮我安装这个 Skill：npx skills add vercel-labs/agent-skills --skill frontend-design"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "如果你拿到的是 Skill 页面链接，也可以直接发给千问办公："]]], ["code", {"uuid": "fg4nwhij2xr1d2szct88", "language": "text-x-markdown"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "帮我安装这个 Skill：https://qoder.com/marketplace/xxx"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "千问办公会尝试识别命令或链接、下载对应文件夹，并把它放到合适的位置。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "安装过程中，如果千问办公问你“安装到用户级还是项目级”，可以按下面的规则选："]]], ["table", {"sr": true, "colsWidth": [244, 244, 244], "uuid": "toqrcpinip2egy7ymosz"}, ["tr", {"uuid": "gikv4ughjgrmhubiiwki", "h": 0}, ["tc", {"vAlign": "top", "uuid": "vs9fkdpxgttd6djvegc8", "hidden": false, "rowSpan": 1, "colSpan": 1}, ["p", {}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "安装位置"]]]], ["tc", {"vAlign": "top", "uuid": "7s1f2jwgggo2c15iof2u", "hidden": false, "rowSpan": 1, "colSpan": 1}, ["p", {}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "适合放什么"]]]], ["tc", {"vAlign": "top", "uuid": "p1io5pph2ffkabt7sjub", "hidden": false, "rowSpan": 1, "colSpan": 1}, ["p", {}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "例子"]]]]], ["tr", {"uuid": "vrj9nxe63gdvysfhnp90", "h": 0}, ["tc", {"vAlign": "top", "uuid": "zhqfaa9d5carz9yxo0dg", "hidden": false, "rowSpan": 1, "colSpan": 1}, ["p", {}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "用户级 Skill"]]]], ["tc", {"vAlign": "top", "uuid": "a0fqkilcpiunr8cw56f3", "hidden": false, "rowSpan": 1, "colSpan": 1}, ["p", {}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "个人在多个项目中复用的方法"]]]], ["tc", {"vAlign": "top", "uuid": "gq8ohyuhd3phfy3tfk9u", "hidden": false, "rowSpan": 1, "colSpan": 1}, ["p", {}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "个人写作风格、常用汇报格式、PPT 偏好"]]]]], ["tr", {"uuid": "yxog105be8a4hncoob1r", "h": 0}, ["tc", {"vAlign": "top", "uuid": "qqc695sn2xjsb200oln9", "hidden": false, "rowSpan": 1, "colSpan": 1}, ["p", {}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "项目级 Skill"]]]], ["tc", {"vAlign": "top", "uuid": "glg8jd6ipfluroi4owhj", "hidden": false, "rowSpan": 1, "colSpan": 1}, ["p", {}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "当前项目或团队共享的方法"]]]], ["tc", {"vAlign": "top", "uuid": "bk2c6mk2gx8ce2bs4o9y", "hidden": false, "rowSpan": 1, "colSpan": 1}, ["p", {}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "客户反馈规范、课程文档写作规范、团队复盘模板"]]]]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "简单判断："]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "fk6mectyrai1", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "只服务于个人习惯，并且多个项目都会用到，选"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "用户级"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "fk6mectyrai1", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "和当前项目强相关，或者希望团队按同一标准使用，选"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "项目级"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "个人 Skill 用来保存自己的写作习惯和常用格式；团队 Skill 用来让多人按同一套标准处理工作；组织或产品负责人维护的 Skill，则适合承载更成熟、需要持续更新的流程。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "这个选择不是一次性决定。以后如果发现放错了范围，通常可以再让 Agent 帮你调整，例如“把这个 Skill 从项目级改成用户级”。"]]], ["h3", {"uuid": "v08lej3qlspwdrd5b87k"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "6.3 创建和修改 Skill 时的自查清单"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "为了减少找不到、误触发和选错 Skill，创建或修改时可以从三方面自查。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "数量和触发"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "uj0mpyqzisxi", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "Skill 不是越多越好"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "：每个 Skill 的 "]], ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "name"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, " 和 "]], ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "description"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, " 都会占用上下文；装得太多，Agent 要看的说明变长，名字和触发条件接近时也更容易选错。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "正文内容"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "2fapusefop7g", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "少写常识，多写判断标准"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "：不要解释 PDF、周报、会议纪要这类 Agent 已经知道的概念，优先写你的栏目、处理规则、例外情况和检查方式。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "2fapusefop7g", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "不要只写人设，要写清步骤"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "：提示词里可以用角色帮助 Agent 理解任务风格，但 Skill 不能只写“你是一位资深专家”。更有用的是写清动作，比如“先读取材料，再按这几个栏目输出；缺少依据的内容标为待确认”。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "2fapusefop7g", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "写当前做法"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "：默认写现在应该怎么做；废弃做法可以单独说明，不要让 Agent 在一堆日期条件里判断该用哪套规则。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "文件组织和任务拆分"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "t6y34b1i0v88", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "SKILL.md"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "只放主要做法"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "：正文里写任务流程、输出格式、判断标准和异常处理；长模板、案例、术语表放到 "]], ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "references/"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "；复杂检查可以放到 "]], ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "scripts/"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "。判断标准是："]], ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "SKILL.md"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, " 正文一旦被 Agent 加载，就会在整个会话中保持在上下文里。每次执行都要用到的核心流程放正文；只在特定情况下才需要的详细参考放单独文件，Agent 会在需要时再去读取。一般建议 "]], ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "SKILL.md"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, " 正文不超过 500 行，接近这个长度时就考虑把部分内容拆到单独文件里。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "t6y34b1i0v88", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "开放任务用文字，精确任务用脚本"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "：写作、审稿、资料整理这类任务，适合用文字说明判断标准；文件批量重命名、表格校验、格式检查这类任务，适合沉淀成脚本。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "t6y34b1i0v88", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "复杂任务可以组合多个 Skill"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "：当一个任务自然分成“收集材料、生成初稿、检查质量、整理发布”等不同环节时，可以让不同 Skill 各负责一段。组合时要写清每个 Skill 的输入、输出和交接结果，例如先用资料整理 Skill 提取事实，再用写作 Skill 生成草稿，最后用检查 Skill 看格式和遗漏。不要为了显得完整而把一个简单流程拆成很多 Skill；如果只是同一类任务里的几个固定步骤，优先放在同一个 Skill 里。"]]], ["h3", {"uuid": "reu5ashg2n44vz855dz8"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "6.4 Skill 管方法，MCP 管能力"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "最后别把 Skill 和工具混在一起。Skill 解决的是“这类工作应该怎么做”。比如写周报时，固定栏目、事项归类、待确认事项怎么写，这些都适合写进 Skill。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "MCP 或外部工具解决的是“Agent 能不能拿到资料、能不能执行动作”。比如读取业务系统、查数据、操作文档、调用服务，这些靠工具能力完成。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "同一个任务里，两者可以一起用。比如做客户拜访准备时，Skill 可以规定：先用企业客户系统 MCP 读取客户最近沟通记录，再用日历 MCP 查可约时间，最后用高德地图 MCP 估算路程，并按“客户背景 / 近期问题 / 拜访时间 / 路线安排”输出。"]]], ["h2", {"uuid": "jlbn1thhjzdt2y0t0qxb", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "动手实验：安装并试用一个别人分享的 Skill"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "e9o6zm"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "周报演示之后，这个实验换一个场景，练习从查找、安装、试用到决定是否保留的完整流程。建议在新会话或临时项目里做，避免影响当前练习环境。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "xpld80kuwvtc", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "从千问办公技能市场、公开 Skills 市场或 GitHub 找一个说明清楚的 Skill。可以选择“读书笔记整理”“Notion 信息图”“前端设计”这类和周报不同的任务。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "xpld80kuwvtc", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "安装前先看它适合什么场景、是否需要读取本地文件、是否会运行脚本、来源页面是否清楚。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "xpld80kuwvtc", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "让千问办公帮你安装；如果提示确认命令、目录或权限，先看清楚再同意。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "xpld80kuwvtc", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "用一个低风险练习任务明确调用它，观察 Agent 是否能找到并使用。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "xpld80kuwvtc", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "如果效果有用，再决定保留；如果频繁误触发、说明模糊或来源不可信，就不要长期使用。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "你需要观察并思考："]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "p4him5nqvfsy", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "这个 Skill 适合处理哪类任务？"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "p4him5nqvfsy", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "它有没有减少你重复交代标准的次数？"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "p4him5nqvfsy", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "它有哪些地方不符合你的习惯？"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "p4him5nqvfsy", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "你会保留它、调整它，还是删除它？"]]], ["h2", {"uuid": "cph8q2j1ydjykkj9u51m", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "进阶实验：用已有规则直接创建一个会议纪要整理 Skill"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "danb2n"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "上一个实验只试用别人分享的 Skill。这个进阶实验换一个不同的创建方式：你已经知道会议纪要该怎么写，直接把规则告诉 Agent，让它生成 Skill。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "周报演示走的是”先跑通再生成”的路径，适合标准还没想清楚的情况。这次反过来：假设你的团队已经有一套固定的会议纪要标准，直接描述需求来创建 Skill。开始前，先在千问办公中选择当前练习项目作为工作目录。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "yt144655rwpg", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "直接把你的会议纪要标准告诉 Agent，让它创建 Skill。可以输入："]]], ["code", {"uuid": "b4a95wp178adnb2ehv7a", "language": "text-x-markdown"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "帮我创建一个项目级”会议纪要整理”Skill，默认生成 Word 会议纪要。规则如下：\n- 固定包含”会议结论 / 待办事项 / 下次跟进 / 待确认事项”四个栏目。\n- 每条待办事项必须写明负责人和截止时间；如果会议记录里没有，标为”待确认”。\n- 没有明确结论的讨论事项，放到”下次跟进”而不是”会议结论”。\n- 请说明 Skill 放在哪里，以及 description 是怎样写的。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "yt144655rwpg", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "生成后检查 "]], ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "SKILL.md"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "。项目级 Skill 通常位于当前工作目录的 "]], ["span", {"data-type": "text"}, ["span", {"code": true, "data-type": "leaf"}, "skills/{skill-name}/SKILL.md"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "。重点看：是否默认生成 Word、是否固定四个栏目、是否说明负责人、截止时间和待确认事项的处理规则。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "yt144655rwpg", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "用下面这段练习材料测试一次，明确调用这个 Skill："]]], ["code", {"uuid": "jyqgn4xvk4wrxiu7p0y5", "language": "latex"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "会议记录：\n1. 下周三前，运营同学补充活动页文案初稿，负责人：李青。\n2. 客服反馈整理表需要增加”问题类型”和”是否影响续费”两列，负责人待确认。\n3. 新版首页发布时间暂定 5 月 28 日，但还要等相关同学确认隐私声明。\n4. 产品介绍页的首屏文案已经定稿。\n5. 下次会议前，需要汇总活动页文案、客服反馈表和首页发布时间三件事的进展。"]]], ["code", {"uuid": "oxhdkatrs0u9ds52b9h6", "language": "text-x-markdown"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "请使用会议纪要整理 Skill，根据上面的会议记录生成一份 Word 会议纪要，文件名为”会议纪要练习.docx”。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "yt144655rwpg", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "检查生成的 Word 内容，看栏目、负责人、截止时间和待确认事项是否符合你写进 Skill 的规则。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "yt144655rwpg", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "换一份会议记录再调用一次，确认输出是否稳定。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "yt144655rwpg", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "如果发现规则写得不够细或遗漏了某些情况，把问题更新到 Skill 对应位置，例如触发说明、执行规则、参考资料或脚本，再调用一次。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "本实验的预期结果不是让 Agent 两次输出完全一样，而是让它在调用会议纪要整理 Skill 时，稳定按你的栏目和判断标准生成 Word 会议纪要。和周报实验对比，你会发现：当规则已经明确时，直接描述需求创建 Skill 比先跑通一次任务更快。"]]], ["h2", {"uuid": "y2q9ytoiqvp0uouq1i3h", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "✅ 本节小结"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "0yfhth"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "Skill 的价值，不是把提示词换个地方保存，而是把一类重复任务的触发条件、执行步骤、输出格式和异常处理规则沉淀下来，让 Agent 下次按同一套方法处理。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "如果周报、会议纪要、资料整理这类任务以后还会反复出现，可以先从技能市场或别人分享的 Skill 里找一个试用；不合适时，再新建自己的 Skill。标准已经明确的，直接描述需求让 Agent 生成；标准还没想清楚的，先在对话里把任务跑顺再提炼。创建后换一份材料测试，把发现的问题更新到对应位置，例如触发说明、执行规则、参考资料或脚本。"]]], ["h2", {"uuid": "8lynh60vpqj2r4efdziv", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "✅ 评价反馈"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "a7o718"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "欢迎你参与"]], ["a", {"href": "https://survey.aliyun.com/apps/zhiliao/ww0sx2B5r"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "阿里云大模型ACA课程调查问卷"]]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "反馈学习体验和课程评价。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "你的批评和鼓励都是我们前进的动力！"]]]]
