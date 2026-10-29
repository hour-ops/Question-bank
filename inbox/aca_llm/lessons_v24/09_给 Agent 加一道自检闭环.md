# 课时9：给 Agent 加一道自检闭环

> 来源：edu.aliyun.com/course/3126500/lesson/344730560

## 🚄 前言

你已经看到 Agent 能拆任务、分头查资料、汇总成一份报告。可只要任务稍微长一点，另一个问题就会冒出来：报告写得很顺，但里面有没有把没完成的事写成完成？有没有遗漏阻塞事项？有没有把不能对外发送的信息写进去？
这类问题不一定靠一句“认真核对一下”就能解决。你需要让 Agent 写完以后，还能拿着依据回头检查一遍。
本课继续用千问办公这类桌面 Agent 演示文件夹读取和任务执行。换成其他支持读取文件夹或上传多个文件的 Agent 时，入口名字可能不同，但判断逻辑相同。
先从一份需要核实的日报初稿开始。

## ✏️ 课程目标

学完这节课后，你将能够：
- 写出执行规则，让 Agent 在执行任务时区分已完成、待确认、阻塞和不能对外发送的信息

- 在生成草稿时同步留下过程记录，写清事项来源、原始记录状态和处理方式

- 把复核中发现的问题补进执行规则或自检清单，减少下次同类错误

## 1 日报初稿容易出什么问题

假设你每天结束工作前都会发一份日报。你把今天的任务记录、客户名单修改记录、会议纪要、报销进度交给 Agent，让它整理成日报。
它给出的初稿可能长这样：
## 2026-05-15 日报

### 已完成

1. 完成客户续费名单整理，已按客户等级标注优先级。

2. 补充“客户回访话术”说明，已更新到团队共享文档。

3. 完成下周客户拜访排期，已和销售同事确认时间。

4. 费用报销材料已提交，后续等待财务打款。

### 明日计划

- 跟进重点客户续费确认。
- 整理本周客户反馈。

### 备注

- 已确认客户采购预算约某预算金额。这份日报看起来顺畅，但发布前需要核实。对照原始记录，会发现几类问题：
日报里的说法
原始记录里的情况
问题

已和销售同事确认下周客户拜访时间
会议纪要写的是“还有两位客户待回复”
把待确认写成已完成

费用报销材料已提交
报销记录写的是“缺少发票，暂未提交”
把阻塞写成已完成

没有风险/阻塞栏目
任务记录里明确有阻塞项
遗漏阻塞事项

这不是格式问题。它真正错在状态和证据：待回复的事被写成确认，缺材料的事被写成提交。还有一类问题是发送范围：备注里的客户预算不该进入日报正文。

## 2 告诉 Agent 什么算合格

上面这些问题——状态写错、证据缺失、不该发的信息混进正文——可以通过一段执行规则来减少。把“什么算合格”写清楚，让 Agent 整理日报时全程遵守：
执行规则：
- 已完成事项必须有证据。
- 进行中、阻塞、待确认不能写成已完成。
- 不能遗漏阻塞事项。
- 私密备注不能进入日报正文、问题清单、过程记录、自检结果等任何输出。执行规则能减少错误，但不能保证输出已经合格。它不是只在开始前生效，而是 Agent 整理材料和生成日报时都要遵守的边界。
规则尽量写成能检查的句子。“内容准确”太宽，“已完成事项必须有证据”就更容易核对。

## 3 生成草稿时同步留下过程记录

为了让后面能检查，不要只让 Agent 给出日报正文，还要让它在旁边列一份过程记录。过程记录不用给别人看，只供你或检查 Agent 判断每个关键内容从哪里来、处于什么状态、能不能写进正文。即使过程记录只给自己看，也不要复述私密备注的具体内容。
这不是固定模板。你也可以换成别的表格列，关键是说清楚：写了什么、依据在哪里、原始记录里显示的状态是什么、这条内容应该怎么处理。比如保留、改写、移到待确认或风险/阻塞栏目，或者删除敏感内容。为了检查方便，先用下面这个表格：
事项｜原始记录状态｜来源文件｜原文线索｜处理方式例如：
事项
原始记录状态
来源文件
原文线索
处理方式

客户续费名单整理
已完成
customer_list_update.md + tasks.md
已按客户等级标注优先级
保留在“已完成”栏目

下周客户拜访排期
待确认
meeting_notes.md + tasks.md
还有两位客户待回复
改到“待确认”栏目，不能写成已完成

费用报销材料
阻塞
reimbursement_notes.md + tasks.md
缺少发票，暂未提交
改到“风险/阻塞”栏目，并说明当前卡在哪里

执行规则用来说明 Agent 必须遵守什么，过程记录用来留下来源、状态和处理方式。没有过程记录，后面检查时就只能凭感觉判断“像不像对”。

## 4 换个对话，专门检查初稿

可以新开一个对话，把初稿、过程记录和必要的原始文件交给它，让它只做检查，不负责写稿。这样职责更单一。
很多检查项可以从执行规则改写而来。执行规则写“已完成事项必须有证据”，检查时就问“每条已完成是否都有证据？”自检清单可以按材料类型调整，这里先用下面这组问题：
自检清单：
1. 每条“已完成”是否有证据？
2. 是否有未完成事项被写成已完成？
3. 是否遗漏阻塞事项？
4. 是否把计划、讨论或承诺误写成结果？
5. 是否泄露或复述不能对外发送的信息？通常你会看到它把问题列出来：
抓到的问题
初稿里的内容
依据

待确认写成已完成
已和销售同事确认下周客户拜访时间
会议纪要写“还有两位客户待回复”

阻塞写成已完成
费用报销材料已提交
报销记录写“缺少发票，暂未提交”

遗漏阻塞事项
初稿没有风险/阻塞栏目
任务记录里有阻塞项

敏感信息进入输出
备注里出现客户采购预算
私密备注写明不得进入日报

自检清单的作用不是“再读一遍”。只说“请认真检查一下”，通常容易得到泛泛的确认；说“按过程记录逐条检查”，更容易让它指出哪个关键内容没有证据、哪条状态写错了。

## 5 把这次问题改成下次能用的检查项

自检发现问题后，先把这份日报改对。但不要停在这里。
检查项不能只记录这次的具体错误。它要回答的是：下次遇到同类材料时，应该查什么。
比如这次发现“客户拜访排期里的待回复被写成已确认”，不要把检查项写成“客户拜访排期有没有写错”。这句话只能查这次日报。把这次独有的对象拿掉，改成：
是否把待回复、待联系、待审批的事项写成已完成或已确认？这样下次材料换成周报、会议纪要或项目进度表，这条检查项仍然能用。
发现问题后，做两件事：
- 先改这次输出：状态写错的改回原始记录里的状态，遗漏的阻塞事项补上，不能对外发送的信息删掉。

- 再补下次检查：规则没说清的，补进执行规则；清单没查到的，补进自检清单；过程记录不够判断的，补一个需要记录的字段。

这不是固定表格，主要是帮你把“这次怎么改”和“下次怎么查”分开。列名可以换，关键是留下三件事：这次发现了什么、这次输出怎么改、下次怎么查同类问题。有时是补一条新检查项，有时是把原来含糊的规则改清楚。
这次发现的问题
这次怎么改
下次怎么查同类问题

把待回复写成已确认
改到“待确认”
自检清单可写成：是否把待回复、待联系、待审批写成已完成或已确认？

把缺发票写成已提交
改到“风险/阻塞”
执行规则可写成：缺材料、待审批、待提交不能写成已完成或已提交

敏感预算进入正文
删除具体内容
执行规则可写成：不能对外发送的信息不得出现在正文、问题清单、过程记录和自检结果里

按上面的处理修订后，日报可以改成这样：
## 2026-05-15 日报

### 已完成

1. 完成客户续费名单整理。
 已按客户等级标注优先级。

2. 补充“客户回访话术”说明。
 已更新到团队共享文档。

### 待确认

3. 下周客户拜访排期。
 部分时间已确认，还有两位客户待回复。

### 风险/阻塞

4. 费用报销材料。
 当前缺少发票，暂未提交。改完之后，再按同一张自检清单查一遍。修订时也可能带来新问题，再查一次是为了确认修订稿也过关。
如果复查又发现新的问题，也按同样方式处理：先修这次输出，再把问题改成下次能用的检查项。

## 6 回看这套自检方法

到这里，这套方法已经串起来了：运行前加载执行规则，生成草稿时同步留下过程记录，草稿完成后对照原始材料检查；发现问题就修订并重新检查，直到自检清单通过。反复出现的问题，还可以整理成通用规则或检查项，供下次任务使用。
在 Agent 领域，这类围绕模型、帮助它按规则完成任务的运行机制通常称为 Harness。Harness 原意是马具：马提供力量，马具负责传递指令、控制方向，并在必要时把它拉住。为了便于理解，可以粗略地把 Agent 看成“模型加上 Harness”：模型负责理解、判断和生成；除了模型本身，Agent 里的其他部分几乎都可以看作 Harness，例如怎样组织指令和上下文、怎样调用工具、怎样控制权限和运行环境，以及怎样检查结果。Claude Code、Codex、千问办公等 Agent 工具，都包含或提供了一套 Harness 能力。

设计并不断改进这套“马具”，让 Agent 更可靠地完成任务，这类工作通常称为 Harness Engineering。文件读取、工具调用、权限控制和沙箱等基础运行机制，通常已经由 Agent 工具提供；但什么样的输出才算合格、应该根据什么检查，需要由人针对任务写清楚。本课讲的正是这一部分：用执行规则明确边界，要求 Agent 留下过程记录，再用自检清单让它核对结果。
前面的检查、修订和复查已经构成一个自检闭环。接下来，看看怎样让这个闭环自动运行。

## 7 让自检闭环自己跑起来

前面的自检闭环包含一组需要反复执行的动作：检查未通过就修订，再重新检查。偶尔使用时，可以由人手动推动；如果每天、每周都要执行，可以把执行规则、处理步骤、过程记录要求、自检清单和输出格式打包成一个 Skill（创建方式详见上一课）。下次明确调用这个 Skill，就不必重新解释整套要求。
如果执行时间也固定，还可以在千问办公里加一个定时任务。创建方式有两种：在对话里用大白话说明（比如“帮我建一个定时任务，每天下午五点，用日报Skill读取今天的材料，跑完整套流程，把草稿和待确认清单留给我”），或者点击左侧导航栏的“定时任务”面板手动填写。
解决了什么时候开始，还得解决什么时候停。停止条件不能只写“改到好为止”，而应同时包括完成条件和强制上限，例如：“自检清单全部通过就停止”；“检查和修订不超过 3 轮”；“达到上限后仍未通过，就输出待确认清单”。明确完成条件和强制上限，可以避免 Agent 过早宣布任务完成，也能防止它反复修改同一段文字，额外消耗 Token 或 Credits。对于付款、对外发送敏感信息、批量或永久删除等可能造成外部影响或难以撤销的操作，建议暂停自动执行，先由人确认。

Skill 负责保存规则和流程，定时任务负责触发，停止条件负责控制什么时候结束。这种让流程自动启动、反复检查和修订，直到满足预设停止条件的做法，有些从业者称为 Loop Engineering（循环工程）。可以这样理解 Harness Engineering 和 Loop Engineering 的关系：Harness Engineering 关注 Agent 执行任务时使用的指令、上下文、工具、权限和检查机制；Loop Engineering 关注怎样让这些机制按条件反复运行，包括循环什么时候开始、根据什么继续、满足什么条件停止。
到这一步，人的角色也从盯着 Agent 一步步干活的“保姆”，转变为这套自检闭环的设计者：设定规则和边界，再审核运行结果。

## 8 用“图”编排多智能体协作应对复杂业务

### 8.1 真实的业务流程很难靠单一 Agent 独立撑起
前面七节我们只在做一件事：用 Harness 和 闭环 让单个业务能稳定运行。但在真实业务工作中，单个业务并不是由单一 Agent 独立负责。以智能客服为例，它绝不是“一个机器人回答所有问题，完成所有操作”。要搭起一套真正能运转的客服系统，你至少需要这些角色同时工作：
- 对话管理：管对话流程（意图识别、分支设计、多轮收集）。

- 流程管理：管业务办理（API 调用、退款、查单）。

- 线索管理：管商机识别和线索收集。

- 质检管理：管质量控制（巡检对话、抽查 Bad Case）。

- 知识管理：管知识库（FAQ 维护、文档更新、答案时效）。

- 数据运营：看运营数据（解决率、转人工率、满意度趋势）。

- 系统管理：管基础配置（权限、租户、资源限额）。

这些角色有着不同的权限、不同的私有数据库，甚至运行在不同的系统里。当业务复杂度提升到需要多角色协作、权限隔离、长周期等待时，我们就需要考虑系统的拓扑结构。

### 8.2 用“图编排”定义多 Agent 团队的协作边界与流转路径
首先需要明确：架构师眼中“图编排”，既不是 LangGraph 这类具体的代码库，也不是 Skill 这种单点手艺。
它的本质，是架构师对多 AI 系统进行的“数据契约（State）与业务卡口（Control）”的规范设计。
把多 Agent 的协作关系画成一张图，定义它们的边界与流转，这就是图编排（Graph Engineering）。在这张图里，我们需要明确：
- 节点（Node）：每个节点代表一个专职 Agent，各司其职。

- 路线（Edge）：定义数据流向，确定谁触发谁、谁给谁喂数据。

- 状态（State）：跨节点流转的共享数据包，记录业务推进的实时进度。

- 检查点（Checkpoint）：设置人工卡口（如知识上线、退款审批）。

有从业者这样总结：循环（Loop）让单个 Agent 的行为可编程，而图（Graph）让 Agent 团队的组织结构可编程。
以下是这支客服团队的拓扑结构：

### 8.3 用状态流转解耦图编排中的业务流与数据流
在这张图的背后，重合着业务流与数据流两层逻辑。在搭建系统时，我们需要把它们分清楚：一层是业务关系拓扑（如设计时定好的角色边界），另一层是数据流 State（如运行时动态流转的工单）。在企业实际落地中，图编排不一定非要用 LangGraph 这类硬编码框架，大型企业往往直接利用现有的消息队列（MQ）、API 或微服务架构来承载这种节点间的数据流转。

#### 业务流定义业务怎么走
也就是我们在图上看到的角色和连线。它规定了客服工作的标准流程：客户提问 ➔ 对话设计判断 ➔ 触发自助办理 ➔ 质检跟进。这是业务的骨架。

#### 数据流定义数据怎么传
在技术实现上，多 Agent 协同不是“传话筒”式的互相发消息，而是共同读写一个共享状态（State）。
你可以把这个 State 理解为一张任务级别的“电子工单”，它随着业务流在节点间运转：
- 工单共享：客户发起咨询时，系统初始化一张工单，里面带着客户问题、识别出的意图、API 办理结果等字段。

- 增量读写：每个节点 Agent 拿到工单后，只处理并更新自己负责的字段。例如，对话 Agent 读取“客户问题”，写下“意图：退款”，再传下去。

- 条件路由：连线（Edge）根据工单上的最新状态决定去向。如果工单写着“意图：退款”，系统会自动投递给自助办理 Agent。任务结束，工单销毁。

#### 临时工单与长期记忆的共存
既然工单（State）是用完即丢的，那团队怎么积累经验？
答案是：工单是临时的，但节点的记忆是长期的。 Agent 在处理工单时，会把学到的知识沉淀在自己的本地数据库中（比如质检 Agent 积累的“避坑清单”），这并不随单次工单的销毁而消失。
- 工作图（Work Graph）：解决“单次任务如何流转”的问题，用完即丢。

- 组织图（Org Graph）：解决“团队如何分工协作”的问题，长期存在，持续沉淀本地经验。

#### 核心价值是收敛状态空间
单 Agent 面对复杂任务时，它的可能走向、历史变量等组合（即“状态空间”）是无限的，极易跑偏或陷入死循环。图编排通过定义这张固定的“工单结构”，把无限的可能性锁死在安全的“状态空间”里，确保系统行为不发散。

### 8.4 固化的节点和路线也会带来流程上的刚性限制
图编排虽然能固化成熟的协作流程，但它不够灵活：
- 重新编排成本高：节点和路线一经画定就无法自主更改。业务流程一旦调整，必须由人工重新连线。

- 缺乏边界外弹性：一旦遇到图纸没覆盖的突发情况，Agent 无法自主协调，极易在死循环中卡死。

🚨 核心原则：非必要不上图，切忌贪大求全！
架构师切记：不要为了追求看似高大上的“系统拓扑”而强行上图。 在业务摸索的“混沌期”，绝大多数场景优先用单 Agent 配合 Loop（自检闭环）就能高效解决；只有当部门分工、数据权限、审批关口完全确定且长期高度稳定后，才值得去构建图编排。

## 🧩 串起一路所学：大模型应用的五层架构
把这一路学的东西摞起来，就是大模型应用的完整五层架构：

Graph 站在最顶层，但不替代任何一层。图上一个节点出错，误差会一路放大。这节课我们搭的执行规则、过程记录、自检清单（属于 Harness 和 Loop 层），就是这张组织图能转起来的地基。
单点 Agent 的高可用是整张图能运转的前提。先做扎实单点，再连点成图。

## 实验：检查一份需要核实的会议纪要初稿

实验目标：用另一种发布材料走一遍“留过程记录 → 按自检清单检查 → 修订 → 整理下次可用的检查项”的流程。
准备材料：
下载并解压会议纪要自检练习文件包。解压后会得到一个 lesson8_minutes_check 文件夹，里面有 6 个 Markdown 文件（以 .md 结尾的纯文本文件）：
- minutes_draft.md：已经生成好的会议纪要初稿，里面故意包含把没完成的事项写成已确认、遗漏阻塞事项和占位敏感项问题。

- work_items.md：任务记录，用来核对事项状态。

- feedback_summary.md：客户反馈摘要，用来核对回访数量和反馈内容。

- meeting_notes.md：回访排期记录，用来核对已确认和待回复客户。

- approval_notes.md：审批记录，用来核对投诉处理方案是否可以对外发送。

- private_notes.md：占位私密备注，用来测试敏感信息过滤。

操作：
把这些文件放进同一个测试文件夹。使用千问办公时，新建任务，点击“选择工作目录”，选择这个文件夹；看到输入框下方出现文件夹名后，粘贴提示词运行。如果使用其他 Agent，就上传这些文件，或选择这个测试文件夹作为可读取目录。
先让 Agent 读初稿，不急着修订：
请先阅读 minutes_draft.md，列出最需要核实的 3 条说法。暂时不要修订。看一下它列出的 3 条：如果都是“已经完成、已经确认、已经通过”这类说法，通常就需要回到其他文件找证据。
如果它只挑了格式问题，没有挑出需要证据支持的说法，可以提醒它优先找“已完成、已确认、已通过”这类说法。
接着让它按证据检查并修订。如果你希望便于检查，可以在提示词最后加一句：请把完整结果写入当前文件夹的 lesson8_result.md。
请检查并修订 minutes_draft.md 这份会议纪要初稿。
对照同一文件夹里的 work_items.md、feedback_summary.md、meeting_notes.md、approval_notes.md 和 private_notes.md：
- 凡是写成“已确认、已通过、已完成”的内容都必须有证据；
- 进行中、阻塞、待确认不能写成已确认；
- 不能遗漏阻塞事项；
- private_notes.md 的具体内容不得出现在会议纪要正文、问题清单、过程记录、自检结果等任何输出中，只能写“已发现并过滤敏感信息”。
请输出：问题清单、修订版会议纪要、过程记录、自检结果、下次可用的检查项、仍需我确认的事项。结果出来后，先看问题清单，再看修订版。重点检查这四处：
- 它有没有把“5 家重点客户已经全部完成回访”改成 3 家已完成、2 家待联系；

- 它有没有把“所有客户确认时间”改成部分确认、部分待回复；

- 它有没有把“投诉处理方案已通过审核”改成风险/阻塞；

- 它有没有删除占位敏感项，并且没有在自检说明里复述具体内容。

再看“下次可用的检查项”：它有没有把这次的具体问题，改写成下次处理同类材料也能使用的问题。
如果它没有给出自检结果，再追加一轮：
请再按下面的自检清单检查一遍，并修订刚才的输出：
1. 每条写成“已确认、已通过、已完成”的内容是否有证据；
2. 是否有未完成事项被写成已确认；
3. 是否遗漏阻塞事项；
4. 是否把计划、讨论或承诺误写成结果；
5. 是否泄露或复述不能对外发送的信息。
如果发现问题，请先修订，再补充下次可用的检查项，然后输出自检结果。最后再做一次人工检查：在输出里搜索 某手机号、某预算金额、某个人评价。如果练习文件里用了其他占位符，也要搜索对应内容。如果这些内容出现在问题清单、过程记录、自检结果或修订说明里，用这句要求重新修订：
敏感信息不能出现在任何输出中。问题清单、过程记录、自检结果、修订说明和最终内容里都只能写“已发现并过滤敏感信息”，不得复述原文、金额、手机号、个人评价或其他具体内容。请重新修订并自检。如果你还发现别的问题，不要只在这次输出里改掉。把它改写成一句下次能直接使用的检查项。例如，不写“这次把 5 家客户都写成已完成”，而写：是否把待联系、待回复、待审批的事项写成已完成或已确认？ 以后处理类似材料时，把这句放进自检清单。

## ✅ 本节小结

下次处理日报、周报、会议纪要时，不要只让 Agent 生成正文。先给执行规则，要求它留下过程记录，再换个对话按清单检查。发现问题后，修这次输出，也把问题补进执行规则或自检清单。
把“生成、检查、修订、再检查”固定下来，下一次就不必由你一轮一轮催着 Agent 做。整理、摘要、草稿、待确认清单这类低风险步骤，可以逐步交给 Agent 按流程自动完成。
非必要不上图。只有涉及多角色协作与长周期审批时才用图编排；绝大多数场景，做扎实单 Agent 的自检闭环就够了。
注意：发送、删除、付款、外发敏感信息这类高风险动作，仍然要等人确认。

## ✅ 评价反馈

欢迎你参与阿里云大模型ACA课程调查问卷反馈学习体验和课程评价。
你的批评和鼓励都是我们前进的动力！

eyJ2IjoxLCJqdGkiOiI2NjY1YjI0MzJlYjM0ZGMwYmViMzlmODc1YzBlMjE5YSIsImxpZCI6MzQ0NzMwNTYwLCJjaWQiOjMxMjY1MDAsInVpZCI6MTQ3MzUzNjI0MjM2MTM2NywiZXhwIjoxNzkxNzM2MTAxfQ.LMYpn5GCqgFGy6jlmo7Nzc_GXp8FNd7nmhcUBjJMQZ0

["root",{},["h2",{"uuid":"yiqqrevnfhy9xtwzvpm6","spacing":{"before":21.333333333333332,"after":12,"line":0.8529411764705882}},["span",{"data-type":"text"},["span",{"bold":true,"sz":16,"szUnit":"pt","data-type":"leaf"},"🚄 前言"]]],["hr",{"color":"#D8D8D8","width":"100%","sz":1,"id":"5bpens"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"你已经看到 Agent 能拆任务、分头查资料、汇总成一份报告。可只要任务稍微长一点，另一个问题就会冒出来：报告写得很顺，但里面有没有把没完成的事写成完成？有没有遗漏阻塞事项？有没有把不能对外发送的信息写进去？"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"这类问题不一定靠一句“认真核对一下”就能解决。你需要让 Agent 写完以后，还能拿着依据回头检查一遍。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"本课继续用千问办公这类桌面 Agent 演示文件夹读取和任务执行。换成其他支持读取文件夹或上传多个文件的 Agent 时，入口名字可能不同，但判断逻辑相同。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"先从一份需要核实的日报初稿开始。"]]],["h2",{"uuid":"chlopiml5mvoilb3jgu5","spacing":{"before":21.333333333333332,"after":12,"line":0.8529411764705882}},["span",{"data-type":"text"},["span",{"bold":true,"sz":16,"szUnit":"pt","data-type":"leaf"},"✏️ 课程目标"]]],["hr",{"color":"#D8D8D8","width":"100%","sz":1,"id":"jefqsu"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"学完这节课后，你将能够："]]],["p",{"spacing":{"line":1.15,"lineRule":"auto"},"list":{"listId":"3uu06xuknhp4","level":0,"isOrdered":false,"isTaskList":false,"listStyleType":"SARR_SDIO_SCIR","symbolStyle":{},"listStyle":{"format":"bullet","text":"➔","align":"left"},"hideSymbol":false}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"写出执行规则，让 Agent 在执行任务时区分已完成、待确认、阻塞和不能对外发送的信息"]]],["p",{"spacing":{"line":1.15,"lineRule":"auto"},"list":{"listId":"3uu06xuknhp4","level":0,"isOrdered":false,"isTaskList":false,"listStyleType":"SARR_SDIO_SCIR","symbolStyle":{},"listStyle":{"format":"bullet","text":"➔","align":"left"},"hideSymbol":false}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"在生成草稿时同步留下过程记录，写清事项来源、原始记录状态和处理方式"]]],["p",{"spacing":{"line":1.15,"lineRule":"auto"},"list":{"listId":"3uu06xuknhp4","level":0,"isOrdered":false,"isTaskList":false,"listStyleType":"SARR_SDIO_SCIR","symbolStyle":{},"listStyle":{"format":"bullet","text":"➔","align":"left"},"hideSymbol":false}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"把复核中发现的问题补进执行规则或自检清单，减少下次同类错误"]]],["h2",{"uuid":"1q36s2x5em8c01drgf9b","spacing":{"before":21.333333333333332,"after":12,"line":0.8529411764705882}},["span",{"data-type":"text"},["span",{"bold":true,"sz":16,"szUnit":"pt","data-type":"leaf"},"1 日报初稿容易出什么问题"]]],["hr",{"color":"#D8D8D8","width":"100%","sz":1,"id":"bmk07b"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"假设你每天结束工作前都会发一份日报。你把今天的任务记录、客户名单修改记录、会议纪要、报销进度交给 Agent，让它整理成日报。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"它给出的初稿可能长这样："]]],["code",{"syntax":"plaintext","theme":"default","uuid":"7txng3qvna1ag9ox3eei","language":"latex"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"## 2026-05-15 日报\n\n### 已完成\n\n1. 完成客户续费名单整理，已按客户等级标注优先级。\n\n2. 补充“客户回访话术”说明，已更新到团队共享文档。\n\n3. 完成下周客户拜访排期，已和销售同事确认时间。\n\n4. 费用报销材料已提交，后续等待财务打款。\n\n### 明日计划\n\n- 跟进重点客户续费确认。\n- 整理本周客户反馈。\n\n### 备注\n\n- 已确认客户采购预算约某预算金额。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"这份日报看起来顺畅，但发布前需要核实。对照原始记录，会发现几类问题："]]],["table",{"sr":true,"colsWidth":[244,244,244],"uuid":"0py414b6c3hgmdretqjz"},["tr",{"uuid":"s1z4yii9z5gutnkyu194","h":0},["tc",{"vAlign":"top","uuid":"v55cu3zphf85tk8hmome","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"bold":true,"data-type":"leaf"},"日报里的说法"]]]],["tc",{"vAlign":"top","uuid":"hhu4wwbpplbo6rp6acpk","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"bold":true,"data-type":"leaf"},"原始记录里的情况"]]]],["tc",{"vAlign":"top","uuid":"derf8dab6on4au8itbyb","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"bold":true,"data-type":"leaf"},"问题"]]]]],["tr",{"uuid":"42wegz0erf2vlxxwno7i","h":0},["tc",{"vAlign":"top","uuid":"rl7ta1ptp07ike58m0hb","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"已和销售同事确认下周客户拜访时间"]]]],["tc",{"vAlign":"top","uuid":"hvpau4jl7e6jkft1lm66","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"会议纪要写的是“还有两位客户待回复”"]]]],["tc",{"vAlign":"top","uuid":"6qlypoanrflg4iiv0nh8","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"把待确认写成已完成"]]]]],["tr",{"uuid":"wq855mah6984u071vp5j","h":0},["tc",{"vAlign":"top","uuid":"5djdlnj3veznjcrbvdg3","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"费用报销材料已提交"]]]],["tc",{"vAlign":"top","uuid":"83goh58q1p0uotc3md3k","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"报销记录写的是“缺少发票，暂未提交”"]]]],["tc",{"vAlign":"top","uuid":"su73k2faso83hvfxeura","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"把阻塞写成已完成"]]]]],["tr",{"uuid":"3dykewzz7zyhberspov7","h":0},["tc",{"vAlign":"top","uuid":"6odwves6h957d9w2fp9k","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"没有风险/阻塞栏目"]]]],["tc",{"vAlign":"top","uuid":"ieum5ekzlw2zbbwkvef2","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"任务记录里明确有阻塞项"]]]],["tc",{"vAlign":"top","uuid":"aw68f1vkikhv5smr9p82","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"遗漏阻塞事项"]]]]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"这不是格式问题。它真正错在状态和证据：待回复的事被写成确认，缺材料的事被写成提交。还有一类问题是发送范围：备注里的客户预算不该进入日报正文。"]]],["h2",{"uuid":"q3barhr44tqjh7el7bjd","spacing":{"before":21.333333333333332,"after":12,"line":0.8529411764705882}},["span",{"data-type":"text"},["span",{"bold":true,"sz":16,"szUnit":"pt","data-type":"leaf"},"2 告诉 Agent 什么算合格"]]],["hr",{"color":"#D8D8D8","width":"100%","sz":1,"id":"6vkq1a"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"上面这些问题——状态写错、证据缺失、不该发的信息混进正文——可以通过一段执行规则来减少。把“什么算合格”写清楚，让 Agent 整理日报时全程遵守："]]],["code",{"syntax":"plaintext","theme":"default","uuid":"aafqb3apa8mc3kvnfuei","language":"latex"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"执行规则：\n- 已完成事项必须有证据。\n- 进行中、阻塞、待确认不能写成已完成。\n- 不能遗漏阻塞事项。\n- 私密备注不能进入日报正文、问题清单、过程记录、自检结果等任何输出。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"执行规则能减少错误，但不能保证输出已经合格。它不是只在开始前生效，而是 Agent 整理材料和生成日报时都要遵守的边界。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"规则尽量写成能检查的句子。“内容准确”太宽，“已完成事项必须有证据”就更容易核对。"]]],["h2",{"uuid":"bc51pvr0oz08ygshf3nn","spacing":{"before":21.333333333333332,"after":12,"line":0.8529411764705882}},["span",{"data-type":"text"},["span",{"bold":true,"sz":16,"szUnit":"pt","data-type":"leaf"},"3 生成草稿时同步留下过程记录"]]],["hr",{"color":"#D8D8D8","width":"100%","sz":1,"id":"ao5xzu"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"为了让后面能检查，不要只让 Agent 给出日报正文，还要让它在旁边列一份过程记录。过程记录不用给别人看，只供你或检查 Agent 判断每个关键内容从哪里来、处于什么状态、能不能写进正文。即使过程记录只给自己看，也不要复述私密备注的具体内容。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"这不是固定模板。你也可以换成别的表格列，关键是说清楚：写了什么、依据在哪里、原始记录里显示的状态是什么、这条内容应该怎么处理。比如保留、改写、移到待确认或风险/阻塞栏目，或者删除敏感内容。为了检查方便，先用下面这个表格："]]],["code",{"syntax":"plaintext","theme":"default","uuid":"rus97l7yyemc41fr24yx","language":"latex"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"事项｜原始记录状态｜来源文件｜原文线索｜处理方式"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"例如："]]],["table",{"sr":true,"colsWidth":[146,146,146,146,146],"uuid":"m6ymqcbm23mw9appm0r4"},["tr",{"uuid":"jip0p9ylr36qyo6m1nwt","h":0},["tc",{"vAlign":"top","uuid":"7htktmlx9psyha7wm7j6","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"bold":true,"data-type":"leaf"},"事项"]]]],["tc",{"vAlign":"top","uuid":"fk0uw91o5xhz7fqvq2kx","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"bold":true,"data-type":"leaf"},"原始记录状态"]]]],["tc",{"vAlign":"top","uuid":"s8do9kut2a82fat7wh91","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"bold":true,"data-type":"leaf"},"来源文件"]]]],["tc",{"vAlign":"top","uuid":"c7aew8r49f8u7ehtb8x3","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"bold":true,"data-type":"leaf"},"原文线索"]]]],["tc",{"vAlign":"top","uuid":"mro6wp2xbf0osp1uxgi6","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"bold":true,"data-type":"leaf"},"处理方式"]]]]],["tr",{"uuid":"zu4o1h4mhvs1l5yi2c9w","h":0},["tc",{"vAlign":"top","uuid":"arh7mz1c9vyn7v7iafk3","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"客户续费名单整理"]]]],["tc",{"vAlign":"top","uuid":"h0keg2qm9tw2q4vm8os6","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"已完成"]]]],["tc",{"vAlign":"top","uuid":"uru10nqp3fq2slyugn7c","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"customer_list_update.md + tasks.md"]]]],["tc",{"vAlign":"top","uuid":"0nt5wecxjp0k7c8bx8aq","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"已按客户等级标注优先级"]]]],["tc",{"vAlign":"top","uuid":"vk826gyclf03w67vjvxn","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"保留在“已完成”栏目"]]]]],["tr",{"uuid":"984iwvxnuwx3xwu1ib3s","h":0},["tc",{"vAlign":"top","uuid":"buvmam53nt767psnp3pg","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"下周客户拜访排期"]]]],["tc",{"vAlign":"top","uuid":"9fdi2wtqow1mdst1c9ds","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"待确认"]]]],["tc",{"vAlign":"top","uuid":"i8ourz248zjmwxmdmsdf","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"meeting_notes.md + tasks.md"]]]],["tc",{"vAlign":"top","uuid":"kc5ymsaadjthls72zfn8","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"还有两位客户待回复"]]]],["tc",{"vAlign":"top","uuid":"p9o3h3jygdpr7ugt9vwy","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"改到“待确认”栏目，不能写成已完成"]]]]],["tr",{"uuid":"tefni3jszhysrts1igkg","h":0},["tc",{"vAlign":"top","uuid":"cxs5gona864m3sinm4ta","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"费用报销材料"]]]],["tc",{"vAlign":"top","uuid":"2m6shgiz2ytod1gdvt2a","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"阻塞"]]]],["tc",{"vAlign":"top","uuid":"7odc7ripat9hvbiiouf2","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"reimbursement_notes.md + tasks.md"]]]],["tc",{"vAlign":"top","uuid":"qzd41a5q3oqof7nbgnp4","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"缺少发票，暂未提交"]]]],["tc",{"vAlign":"top","uuid":"peivdualct0yil3bcl7e","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"改到“风险/阻塞”栏目，并说明当前卡在哪里"]]]]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"执行规则用来说明 Agent 必须遵守什么，过程记录用来留下来源、状态和处理方式。没有过程记录，后面检查时就只能凭感觉判断“像不像对”。"]]],["h2",{"uuid":"0n7q5bon0qhb7l85ea6j","spacing":{"before":21.333333333333332,"after":12,"line":0.8529411764705882}},["span",{"data-type":"text"},["span",{"bold":true,"sz":16,"szUnit":"pt","data-type":"leaf"},"4 换个对话，专门检查初稿"]]],["hr",{"color":"#D8D8D8","width":"100%","sz":1,"id":"d4d07u"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"可以新开一个对话，把初稿、过程记录和必要的原始文件交给它，让它只做检查，不负责写稿。这样职责更单一。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"很多检查项可以从执行规则改写而来。执行规则写“已完成事项必须有证据”，检查时就问“每条已完成是否都有证据？”自检清单可以按材料类型调整，这里先用下面这组问题："]]],["code",{"syntax":"plaintext","theme":"default","uuid":"soazpi72ktneee3rfb7y","language":"latex"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"自检清单：\n1. 每条“已完成”是否有证据？\n2. 是否有未完成事项被写成已完成？\n3. 是否遗漏阻塞事项？\n4. 是否把计划、讨论或承诺误写成结果？\n5. 是否泄露或复述不能对外发送的信息？"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"通常你会看到它把问题列出来："]]],["table",{"sr":true,"colsWidth":[244,244,244],"uuid":"xzrsvsz3u9uxpm0nphai"},["tr",{"uuid":"lpnt4lr8c4eore1gsyqz","h":0},["tc",{"vAlign":"top","uuid":"ygn0ojmtigeyuxa2amk9","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"bold":true,"data-type":"leaf"},"抓到的问题"]]]],["tc",{"vAlign":"top","uuid":"f7tc1v1f063rptsrcjk0","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"bold":true,"data-type":"leaf"},"初稿里的内容"]]]],["tc",{"vAlign":"top","uuid":"zqz9czsj1g0ncw3i2aln","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"bold":true,"data-type":"leaf"},"依据"]]]]],["tr",{"uuid":"c0umlf57mdzy0e2fj9n4","h":0},["tc",{"vAlign":"top","uuid":"bhhprgkix83pldr4wkb7","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"待确认写成已完成"]]]],["tc",{"vAlign":"top","uuid":"ini3ylopsdo1298tfss9","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"已和销售同事确认下周客户拜访时间"]]]],["tc",{"vAlign":"top","uuid":"ljp1mp9a1etf7efdg7aa","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"会议纪要写“还有两位客户待回复”"]]]]],["tr",{"uuid":"7oxf1x0xxj80nxbmrceg","h":0},["tc",{"vAlign":"top","uuid":"ynzk72u4k5m04vfmc4kx","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"阻塞写成已完成"]]]],["tc",{"vAlign":"top","uuid":"qqwb37exf1ww5b94gybn","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"费用报销材料已提交"]]]],["tc",{"vAlign":"top","uuid":"wd7cemw8gxcrfozf4yfu","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"报销记录写“缺少发票，暂未提交”"]]]]],["tr",{"uuid":"q3lm6c4wcm6qrne38gd7","h":0},["tc",{"vAlign":"top","uuid":"splixk9ezhxk8cj04nha","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"遗漏阻塞事项"]]]],["tc",{"vAlign":"top","uuid":"77en7pnpbizy5saecwf5","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"初稿没有风险/阻塞栏目"]]]],["tc",{"vAlign":"top","uuid":"53ev6xjz6ctk4goguf1q","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"任务记录里有阻塞项"]]]]],["tr",{"uuid":"e15ddip2umxlfqu4rbaj","h":0},["tc",{"vAlign":"top","uuid":"th5faccuy011ahjp4asg","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"敏感信息进入输出"]]]],["tc",{"vAlign":"top","uuid":"qk16cmy53ms364d1u4xe","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"备注里出现客户采购预算"]]]],["tc",{"vAlign":"top","uuid":"c9np7j1m63y53p6cbckm","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"私密备注写明不得进入日报"]]]]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"自检清单的作用不是“再读一遍”。只说“请认真检查一下”，通常容易得到泛泛的确认；说“按过程记录逐条检查”，更容易让它指出哪个关键内容没有证据、哪条状态写错了。"]]],["h2",{"uuid":"nnmp38ixus4ekn53sbke","spacing":{"before":21.333333333333332,"after":12,"line":0.8529411764705882}},["span",{"data-type":"text"},["span",{"bold":true,"sz":16,"szUnit":"pt","data-type":"leaf"},"5 把这次问题改成下次能用的检查项"]]],["hr",{"color":"#D8D8D8","width":"100%","sz":1,"id":"ddc9cg"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"自检发现问题后，先把这份日报改对。但不要停在这里。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"检查项不能只记录这次的具体错误。它要回答的是：下次遇到同类材料时，应该查什么。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"比如这次发现“客户拜访排期里的待回复被写成已确认”，不要把检查项写成“客户拜访排期有没有写错”。这句话只能查这次日报。把这次独有的对象拿掉，改成："]]],["code",{"syntax":"plaintext","theme":"default","uuid":"27v9dpz3n25g3wlyvigf","language":"latex"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"是否把待回复、待联系、待审批的事项写成已完成或已确认？"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"这样下次材料换成周报、会议纪要或项目进度表，这条检查项仍然能用。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"发现问题后，做两件事："]]],["p",{"spacing":{"line":1.15,"lineRule":"auto"},"list":{"listId":"wb68vdv3ieyt","level":0,"isOrdered":false,"isTaskList":false,"listStyleType":"SARR_SDIO_SCIR","symbolStyle":{},"listStyle":{"format":"bullet","text":"➔","align":"left"},"hideSymbol":false}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"先改这次输出：状态写错的改回原始记录里的状态，遗漏的阻塞事项补上，不能对外发送的信息删掉。"]]],["p",{"spacing":{"line":1.15,"lineRule":"auto"},"list":{"listId":"wb68vdv3ieyt","level":0,"isOrdered":false,"isTaskList":false,"listStyleType":"SARR_SDIO_SCIR","symbolStyle":{},"listStyle":{"format":"bullet","text":"➔","align":"left"},"hideSymbol":false}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"再补下次检查：规则没说清的，补进执行规则；清单没查到的，补进自检清单；过程记录不够判断的，补一个需要记录的字段。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"这不是固定表格，主要是帮你把“这次怎么改”和“下次怎么查”分开。列名可以换，关键是留下三件事：这次发现了什么、这次输出怎么改、下次怎么查同类问题。有时是补一条新检查项，有时是把原来含糊的规则改清楚。"]]],["table",{"sr":true,"colsWidth":[244,244,244],"uuid":"8l771v5kb43jl25dopqq"},["tr",{"uuid":"nuw2k4mc3lis1gohevgr","h":0},["tc",{"vAlign":"top","uuid":"bhk1tcp95wvi62ohplww","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"bold":true,"data-type":"leaf"},"这次发现的问题"]]]],["tc",{"vAlign":"top","uuid":"s541rx8caxi6yef0o53c","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"bold":true,"data-type":"leaf"},"这次怎么改"]]]],["tc",{"vAlign":"top","uuid":"a9cz3rl0ta4wlqz3brnx","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"bold":true,"data-type":"leaf"},"下次怎么查同类问题"]]]]],["tr",{"uuid":"xbt0iq452xqusyq3udsj","h":0},["tc",{"vAlign":"top","uuid":"wfaafzyt9lqyzix8r9dy","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"把待回复写成已确认"]]]],["tc",{"vAlign":"top","uuid":"it07lg66wy9103lhbgi7","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"改到“待确认”"]]]],["tc",{"vAlign":"top","uuid":"2l2h33osi9tr8c4chvkr","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"自检清单可写成：是否把待回复、待联系、待审批写成已完成或已确认？"]]]]],["tr",{"uuid":"noh1tuo0fai3iq8iqezz","h":0},["tc",{"vAlign":"top","uuid":"8n90opcuk03xgpkrf7s1","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"把缺发票写成已提交"]]]],["tc",{"vAlign":"top","uuid":"x89g3yl06jqx5i9a6k9i","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"改到“风险/阻塞”"]]]],["tc",{"vAlign":"top","uuid":"rn7qsxegc7iy09o74od3","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"执行规则可写成：缺材料、待审批、待提交不能写成已完成或已提交"]]]]],["tr",{"uuid":"wckgxpz7k3n6mimbmaps","h":0},["tc",{"vAlign":"top","uuid":"r89r65zrllbv4i0mnqp2","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"敏感预算进入正文"]]]],["tc",{"vAlign":"top","uuid":"hbjbwvu90wox7468zi32","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"删除具体内容"]]]],["tc",{"vAlign":"top","uuid":"scw70ta6ti9ykhw5qspm","hidden":false,"rowSpan":1,"colSpan":1},["p",{},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"执行规则可写成：不能对外发送的信息不得出现在正文、问题清单、过程记录和自检结果里"]]]]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"按上面的处理修订后，日报可以改成这样："]]],["code",{"syntax":"plaintext","theme":"default","uuid":"kuvb8eavpcoerm6kz16f","language":"latex"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"## 2026-05-15 日报\n\n### 已完成\n\n1. 完成客户续费名单整理。\n 已按客户等级标注优先级。\n\n2. 补充“客户回访话术”说明。\n 已更新到团队共享文档。\n\n### 待确认\n\n3. 下周客户拜访排期。\n 部分时间已确认，还有两位客户待回复。\n\n### 风险/阻塞\n\n4. 费用报销材料。\n 当前缺少发票，暂未提交。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"改完之后，再按同一张自检清单查一遍。修订时也可能带来新问题，再查一次是为了确认修订稿也过关。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"如果复查又发现新的问题，也按同样方式处理：先修这次输出，再把问题改成下次能用的检查项。"]]],["h2",{"uuid":"tvbiruh2bx909re17bbn","spacing":{"before":21.333333333333332,"after":12,"line":0.8529411764705882}},["span",{"data-type":"text"},["span",{"bold":true,"sz":16,"szUnit":"pt","data-type":"leaf"},"6 回看这套自检方法"]]],["hr",{"color":"#D8D8D8","width":"100%","sz":1,"id":"in14pv"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"到这里，这套方法已经串起来了：运行前加载执行规则，生成草稿时同步留下过程记录，草稿完成后对照原始材料检查；发现问题就修订并重新检查，直到自检清单通过。反复出现的问题，还可以整理成通用规则或检查项，供下次任务使用。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"在 Agent 领域，这类围绕模型、帮助它按规则完成任务的运行机制通常称为 "],["span",{"bold":true,"data-type":"leaf"},"Harness"],["span",{"data-type":"leaf"},"。Harness 原意是马具：马提供力量，马具负责传递指令、控制方向，并在必要时把它拉住。为了便于理解，可以粗略地把 Agent 看成“模型加上 Harness”：模型负责理解、判断和生成；除了模型本身，Agent 里的其他部分几乎都可以看作 Harness，例如怎样组织指令和上下文、怎样调用工具、怎样控制权限和运行环境，以及怎样检查结果。Claude Code、Codex、千问办公等 Agent 工具，都包含或提供了一套 Harness 能力。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]],["img",{"id":"6dy2og","src":"https://img.alicdn.com/imgextra/i1/O1CN017Ngd7V1GJJBhMMJK1_!!6000000000601-2-tps-1792-608.png","width":800,"height":271,"rotation":0},["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]]],["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"设计并不断改进这套“马具”，让 Agent 更可靠地完成任务，这类工作通常称为 "],["span",{"bold":true,"data-type":"leaf"},"Harness Engineering"],["span",{"data-type":"leaf"},"。文件读取、工具调用、权限控制和沙箱等基础运行机制，通常已经由 Agent 工具提供；但什么样的输出才算合格、应该根据什么检查，需要由人针对任务写清楚。本课讲的正是这一部分：用执行规则明确边界，要求 Agent 留下过程记录，再用自检清单让它核对结果。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"前面的检查、修订和复查已经构成一个自检闭环。接下来，看看怎样让这个闭环自动运行。"]]],["h2",{"uuid":"5ixfcwra4p8i4eosslqy","spacing":{"before":21.333333333333332,"after":12,"line":0.8529411764705882}},["span",{"data-type":"text"},["span",{"bold":true,"sz":16,"szUnit":"pt","data-type":"leaf"},"7 让自检闭环自己跑起来"]]],["hr",{"color":"#D8D8D8","width":"100%","sz":1,"id":"bgfz5x"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"前面的自检闭环包含一组需要反复执行的动作：检查未通过就修订，再重新检查。偶尔使用时，可以由人手动推动；如果每天、每周都要执行，可以把执行规则、处理步骤、过程记录要求、自检清单和输出格式打包成一个 "],["span",{"bold":true,"data-type":"leaf"},"Skill"],["span",{"data-type":"leaf"},"（创建方式详见上一课）。下次明确调用这个 Skill，就不必重新解释整套要求。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"如果执行时间也固定，还可以在千问办公里加一个"],["span",{"bold":true,"data-type":"leaf"},"定时任务"],["span",{"data-type":"leaf"},"。创建方式有两种：在对话里用大白话说明（比如“帮我建一个定时任务，每天下午五点，用日报Skill读取今天的材料，跑完整套流程，把草稿和待确认清单留给我”），或者点击左侧导航栏的“定时任务”面板手动填写。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"解决了什么时候开始，还得解决什么时候停。"],["span",{"bold":true,"data-type":"leaf"},"停止条件"],["span",{"data-type":"leaf"},"不能只写“改到好为止”，而应同时包括完成条件和强制上限，例如：“自检清单全部通过就停止”；“检查和修订不超过 3 轮”；“达到上限后仍未通过，就输出待确认清单”。明确完成条件和强制上限，可以避免 Agent 过早宣布任务完成，也能防止它反复修改同一段文字，额外消耗 Token 或 Credits。对于付款、对外发送敏感信息、批量或永久删除等可能造成外部影响或难以撤销的操作，建议暂停自动执行，先由人确认。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]],["img",{"id":"fnnb9h","src":"https://img.alicdn.com/imgextra/i1/O1CN0185HJAo1zqQXOR7aHx_!!6000000006765-2-tps-1792-608.png","width":800,"height":271,"rotation":0},["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]]],["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"Skill 负责保存规则和流程，定时任务负责触发，停止条件负责控制什么时候结束。这种让流程自动启动、反复检查和修订，直到满足预设停止条件的做法，有些从业者称为 "],["span",{"bold":true,"data-type":"leaf"},"Loop Engineering"],["span",{"data-type":"leaf"},"（循环工程）。可以这样理解 "],["span",{"bold":true,"data-type":"leaf"},"Harness Engineering"],["span",{"data-type":"leaf"}," 和 "],["span",{"bold":true,"data-type":"leaf"},"Loop Engineering"],["span",{"data-type":"leaf"}," 的关系：Harness Engineering 关注 Agent 执行任务时使用的指令、上下文、工具、权限和检查机制；Loop Engineering 关注怎样让这些机制按条件反复运行，包括循环什么时候开始、根据什么继续、满足什么条件停止。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"到这一步，人的角色也从盯着 Agent 一步步干活的“保姆”，转变为这套自检闭环的设计者：设定规则和边界，再审核运行结果。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]]],["h2",{"uuid":"ms64fy2ep8bqkrut14"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"8 用“图”编排多智能体协作应对复杂业务"]]],["hr",{"color":"#D8D8D8","width":"100%","sz":1,"id":"bgfz5x"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]]],["h3",{"uuid":"ms64fy2ep8bqkrut14","spacing":{"before":18.666666666666668,"after":12,"line":0.8529411764705882}},["span",{"data-type":"text"},["span",{"bold":true,"sz":14,"szUnit":"pt","data-type":"leaf"},"8.1 真实的业务流程很难靠单一 Agent 独立撑起"]]],["p",{"uuid":"ms64fy2e8c9t05489n6"},["span",{"data-type":"text"},["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"前面七节我们只在做一件事：用 Harness 和 闭环 让"],["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"单个业务能稳定运行"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"。但在真实业务工作中，单个业务并不是由单一 Agent 独立负责。以"],["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"智能客服"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"为例，它绝不是“一个机器人回答所有问题，完成所有操作”。要搭起一套真正能运转的客服系统，你至少需要这些角色同时工作："]]],["p",{"list":{"isOrdered":false,"level":0,"listId":"fth03f9wlgt","listStyle":{"align":"left","format":"bullet","text":"●"},"symbolStyle":{"sz":11}},"ind":{"left":32}},["span",{"data-type":"text"},["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"对话管理"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"：管对话流程（意图识别、分支设计、多轮收集）。"]]],["p",{"list":{"isOrdered":false,"level":0,"listId":"fth03f9wlgt","listStyle":{"align":"left","format":"bullet","text":"●"},"symbolStyle":{"sz":11}},"ind":{"left":32}},["span",{"data-type":"text"},["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"流程管理"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"：管业务办理（API 调用、退款、查单）。"]]],["p",{"list":{"isOrdered":false,"level":0,"listId":"fth03f9wlgt","listStyle":{"align":"left","format":"bullet","text":"●"},"symbolStyle":{"sz":11}},"ind":{"left":32}},["span",{"data-type":"text"},["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"线索管理"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"：管商机识别和线索收集。"]]],["p",{"list":{"isOrdered":false,"level":0,"listId":"fth03f9wlgt","listStyle":{"align":"left","format":"bullet","text":"●"},"symbolStyle":{"sz":11}},"ind":{"left":32}},["span",{"data-type":"text"},["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"质检管理"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"：管质量控制（巡检对话、抽查 Bad Case）。"]]],["p",{"list":{"isOrdered":false,"level":0,"listId":"fth03f9wlgt","listStyle":{"format":"bullet","text":"●","align":"left"},"symbolStyle":{"sz":11}},"ind":{"left":32}},["span",{"data-type":"text"},["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"知识管理"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"：管知识库（FAQ 维护、文档更新、答案时效）。"]]],["p",{"list":{"isOrdered":false,"level":0,"listId":"fth03f9wlgt","listStyle":{"align":"left","format":"bullet","text":"●"},"symbolStyle":{"sz":11}},"ind":{"left":32}},["span",{"data-type":"text"},["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"数据运营"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"：看运营数据（解决率、转人工率、满意度趋势）。"]]],["p",{"list":{"isOrdered":false,"level":0,"listId":"fth03f9wlgt","listStyle":{"align":"left","format":"bullet","text":"●"},"symbolStyle":{"sz":11}},"ind":{"left":32}},["span",{"data-type":"text"},["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"系统管理"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"：管基础配置（权限、租户、资源限额）。"]]],["p",{"uuid":"ms64k86bqru2gn4ce0l"},["span",{"data-type":"text"},["span",{"color":"rgb(27, 27, 30)","sz":11,"szUnit":"pt","data-type":"leaf"},"这些角色有着不同的权限、不同的私有数据库，甚至运行在不同的系统里。当业务复杂度提升到需要"],["span",{"bold":true,"color":"rgb(27, 27, 30)","sz":11,"szUnit":"pt","data-type":"leaf"},"多角色协作、权限隔离、长周期等待"],["span",{"color":"rgb(27, 27, 30)","sz":11,"szUnit":"pt","data-type":"leaf"},"时，我们就需要考虑系统的拓扑结构。"]]],["h3",{"uuid":"ms64fy2f7aapg51tmyf"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"8.2 用“图编排”定义多 Agent 团队的协作边界与流转路径"]]],["p",{"uuid":"ms64fy2f6o5ifm2j0ks"},["span",{"data-type":"text"},["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"首先需要明确：架构师眼中“图编排”，既不是 LangGraph 这类具体的代码库，也不是 Skill 这种单点手艺。\n它的本质，是架构师对多 AI 系统进行的"],["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"“数据契约（State）"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"与"],["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"业务卡口（Control）”"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"的规范设计。"]]],["p",{"uuid":"ms72yagrarufxzrt8i"},["span",{"data-type":"text"},["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"把多 Agent 的协作关系画成一张图，定义它们的边界与流转，这就是"],["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"图编排（Graph Engineering）"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"。在这张图里，我们需要明确："]]],["p",{"list":{"listId":"c0rv97ky3h","isOrdered":true,"level":0,"listStyle":{"format":"decimal","text":"%1.","align":"left"},"symbolStyle":{"sz":11}},"ind":{"left":32}},["span",{"data-type":"text"},["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"节点（Node）"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"：每个节点代表一个专职 Agent，各司其职。"]]],["p",{"list":{"listId":"c0rv97ky3h","isOrdered":true,"level":0,"listStyle":{"format":"decimal","text":"%1.","align":"left"},"symbolStyle":{"sz":11}},"ind":{"left":32}},["span",{"data-type":"text"},["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"路线（Edge）"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"：定义数据流向，确定谁触发谁、谁给谁喂数据。"]]],["p",{"list":{"listId":"c0rv97ky3h","isOrdered":true,"level":0,"listStyle":{"format":"decimal","text":"%1.","align":"left"},"extraData":{},"isChecked":false,"hideSymbol":false,"symbolStyle":{"sz":11}},"ind":{"left":32}},["span",{"data-type":"text"},["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"状态（State）"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"：跨节点流转的共享数据包，记录业务推进的实时进度。"]]],["p",{"list":{"listId":"c0rv97ky3h","isOrdered":true,"level":0,"listStyle":{"format":"decimal","text":"%1.","align":"left"},"symbolStyle":{"sz":11}},"ind":{"left":32}},["span",{"data-type":"text"},["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"检查点（Checkpoint）"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"：设置人工卡口（如知识上线、退款审批）。"]]],["p",{"uuid":"ms64mu95461eryuyh5h"},["span",{"data-type":"text"},["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"有从业者这样总结："]],["a",{"href":"https://explainx.ai/blog/graph-engineering-ai-agents-multi-agent-organizations-2026","uuid":"ms64mv4unuo57ssudcc"},["span",{"data-type":"text"},["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"循环（Loop）让单个 Agent 的行为可编程，而图（Graph）让 Agent 团队的组织结构可编程"]]],["span",{"data-type":"text"},["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"。"]]],["p",{"uuid":"ms759y5u1tfmvjraie1i"},["span",{"data-type":"text"},["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"以下是这支客服团队的拓扑结构："]]],["p",{"uuid":"ms64s1nk3yyqozxswos"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]],["img",{"id":"not3rc","name":"graph-orchestration-service-grid.svg","size":11721,"width":850,"height":567,"src":"https://scms-prod-sh-public.oss-cn-shanghai.aliyuncs.com/course_picture/laaofzpvjyfbnkoqicnt.svg","rotation":0},["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]]],["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]]],["h3",{"uuid":"ms64fy2gla00hdk15wm"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"8.3 用状态流转解耦图编排中的业务流与数据流"]]],["p",{"uuid":"ms6xx01i637mgle9ty2"},["span",{"data-type":"text"},["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"在这张图的背后，重合着业务流与数据流两层逻辑。在搭建系统时，我们需要把它们分清楚"],["span",{"color":"rgb(27, 27, 30)","sz":11,"szUnit":"pt","data-type":"leaf"},"：一层是"],["span",{"bold":true,"color":"rgb(27, 27, 30)","sz":11,"szUnit":"pt","data-type":"leaf"},"业务关系拓扑（如设计时定好的角色边界）"],["span",{"color":"rgb(27, 27, 30)","sz":11,"szUnit":"pt","data-type":"leaf"},"，另一层是"],["span",{"bold":true,"color":"rgb(27, 27, 30)","sz":11,"szUnit":"pt","data-type":"leaf"},"数据流 State（如运行时动态流转的工单）"],["span",{"color":"rgb(27, 27, 30)","sz":11,"szUnit":"pt","data-type":"leaf"},"。在企业实际落地中，图编排不一定非要用 LangGraph 这类硬编码框架，大型企业往往直接利用现有的消息队列（MQ）、API 或微服务架构来承载这种节点间的数据流转。"]]],["h4",{"uuid":"ms6xx01jqu5cyljvfkh"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"业务流定义业务怎么走"]]],["p",{"uuid":"ms6xx01jwb7zrwnrrm"},["span",{"data-type":"text"},["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"也就是我们在图上看到的角色和连线。它规定了客服工作的标准流程：客户提问 ➔ 对话设计判断 ➔ 触发自助办理 ➔ 质检跟进。这是业务的骨架。"]]],["h4",{"uuid":"ms6xx01jpz9t1ktnal"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"数据流定义数据怎么传"]]],["p",{"uuid":"ms6xx01kyninuuwxs4"},["span",{"data-type":"text"},["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"在技术实现上，多 Agent 协同不是“传话筒”式的互相发消息，而是共同读写一个"],["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"共享状态（State）"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"。"]]],["p",{"uuid":"ms6xx01kii7cypzzu3"},["span",{"data-type":"text"},["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"你可以把这个 State 理解为一张"],["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"任务级别的“电子工单”"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"，它随着业务流在节点间运转："]]],["p",{"list":{"listId":"z1aiqgj6y2","isOrdered":false,"level":0,"listStyle":{"format":"bullet","text":"●","align":"left"},"symbolStyle":{"sz":11}},"ind":{"left":32}},["span",{"data-type":"text"},["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"工单共享"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"：客户发起咨询时，系统初始化一张工单，里面带着客户问题、识别出的意图、API 办理结果等字段。"]]],["p",{"list":{"listId":"z1aiqgj6y2","isOrdered":false,"level":0,"listStyle":{"format":"bullet","text":"●","align":"left"},"symbolStyle":{"sz":11}},"ind":{"left":32}},["span",{"data-type":"text"},["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"增量读写"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"：每个节点 Agent 拿到工单后，只处理并更新自己负责的字段。例如，对话 Agent 读取“客户问题”，写下“意图：退款”，再传下去。"]]],["p",{"list":{"listId":"z1aiqgj6y2","isOrdered":false,"level":0,"listStyle":{"format":"bullet","text":"●","align":"left"},"symbolStyle":{"sz":11}},"ind":{"left":32}},["span",{"data-type":"text"},["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"条件路由"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"：连线（Edge）根据工单上的最新状态决定去向。如果工单写着“意图：退款”，系统会自动投递给自助办理 Agent。任务结束，工单销毁。"]]],["h4",{"uuid":"ms6xx01ke6afc1uwr9a"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"临时工单与长期记忆的共存"]]],["p",{"uuid":"ms6xx01kf1khow5xdio"},["span",{"data-type":"text"},["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"既然工单（State）是用完即丢的，那团队怎么积累经验？\n答案是："],["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"工单是临时的，但节点的记忆是长期的。"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"}," Agent 在处理工单时，会把学到的知识沉淀在自己的本地数据库中（比如质检 Agent 积累的“避坑清单”），这并不随单次工单的销毁而消失。"]]],["p",{"list":{"listId":"664dbvmw92g","isOrdered":false,"level":0,"listStyle":{"format":"bullet","text":"●","align":"left"},"symbolStyle":{"sz":11}},"ind":{"left":32}},["span",{"data-type":"text"},["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"工作图（Work Graph）"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"：解决“单次任务如何流转”的问题，用完即丢。"]]],["p",{"list":{"listId":"664dbvmw92g","isOrdered":false,"level":0,"listStyle":{"format":"bullet","text":"●","align":"left"},"symbolStyle":{"sz":11}},"ind":{"left":32}},["span",{"data-type":"text"},["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"组织图（Org Graph）"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"：解决“团队如何分工协作”的问题，长期存在，持续沉淀本地经验。"]]],["h4",{"uuid":"ms6xx01lsr7ijabepjh"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"核心价值是收敛状态空间"]]],["p",{"uuid":"ms6xx01ll2h2p77wvr"},["span",{"data-type":"text"},["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"单 Agent 面对复杂任务时，它的可能走向、历史变量等组合（即“状态空间”）是无限的，极易跑偏或陷入死循环。图编排通过定义这张固定的“工单结构”，把无限的可能性锁死在安全的“状态空间”里，确保系统行为不发散。"]]],["h3",{"uuid":"ms64fy2gtdujvmdtw6"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"8.4 固化的节点和路线也会带来流程上的刚性限制"]]],["p",{"uuid":"ms64fy2gfi1hd62cwnh"},["span",{"data-type":"text"},["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"图编排虽然能固化成熟的协作流程，但它不够灵活："]]],["p",{"list":{"listId":"013xxcqksczfj","isOrdered":false,"level":0,"listStyle":{"format":"bullet","text":"●","align":"left"},"symbolStyle":{"sz":11}},"ind":{"left":32}},["span",{"data-type":"text"},["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"重新编排成本高"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"：节点和路线一经画定就无法自主更改。业务流程一旦调整，必须由人工重新连线。"]]],["p",{"list":{"listId":"013xxcqksczfj","isOrdered":false,"level":0,"listStyle":{"format":"bullet","text":"●","align":"left"},"extraData":{},"isChecked":false,"hideSymbol":false,"symbolStyle":{"sz":11}},"ind":{"left":32}},["span",{"data-type":"text"},["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"缺乏边界外弹性"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"：一旦遇到图纸没覆盖的突发情况，Agent 无法自主协调，极易在死循环中卡死。"]]],["table",{"colsWidth":[737]},["tr",{},["tc",{"colSpan":1,"rowSpan":1},["p",{"uuid":"ms64fy2h9yfrmyxvjye","blockquote":false},["span",{"data-type":"text"},["span",{"color":"rgb(27, 27, 30)","sz":11,"szUnit":"pt","data-type":"leaf"},"🚨 "],["span",{"bold":true,"color":"rgb(27, 27, 30)","sz":11,"szUnit":"pt","data-type":"leaf"},"核心原则：非必要不上图，切忌贪大求全！"]]],["p",{"blockquote":false,"uuid":"ms72uyhp3tfdi2iexdv"},["span",{"data-type":"text"},["span",{"color":"rgb(27, 27, 30)","sz":11,"szUnit":"pt","data-type":"leaf"},"架构师切记："],["span",{"bold":true,"color":"rgb(27, 27, 30)","sz":11,"szUnit":"pt","data-type":"leaf"},"不要为了追求看似高大上的“系统拓扑”而强行上图。"],["span",{"color":"rgb(27, 27, 30)","sz":11,"szUnit":"pt","data-type":"leaf"}," 在业务摸索的“混沌期”，绝大多数场景优先用单 Agent 配合 Loop（自检闭环）就能高效解决；只有当部门分工、数据权限、审批关口完全确定且长期高度稳定后，才值得去构建图编排。"]]]]]],["p",{},["span",{"data-type":"text"},["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},""]]],["h2",{"uuid":"ms64fy2hsggwmuhpnca","spacing":{"before":21.333333333333332,"after":12,"line":0.8529411764705882}},["span",{"data-type":"text"},["span",{"bold":true,"sz":16,"szUnit":"pt","data-type":"leaf"},"🧩 串起一路所学：大模型应用的五层架构"]]],["p",{"uuid":"ms64fy2hdj27gqrlgeg"},["span",{"data-type":"text"},["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"把这一路学的东西摞起来，就是大模型应用的完整五层架构："]]],["p",{"uuid":"ms64hwgi0tw8gm5lce5"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]],["img",{"id":"mgyesw","name":"five-layer-stack.svg","size":4102,"width":850,"height":478,"src":"https://scms-prod-sh-public.oss-cn-shanghai.aliyuncs.com/course_picture/igwmftvzzuwdynuvryae.svg","rotation":0},["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]]],["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]]],["p",{"uuid":"ms64fy2h7s10t3k5hx"},["span",{"data-type":"text"},["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"Graph 站在最顶层，但不替代任何一层。图上一个节点出错，误差会一路放大。这节课我们搭的"],["span",{"bold":true,"sz":11,"szUnit":"pt","data-type":"leaf"},"执行规则、过程记录、自检清单"],["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"（属于 Harness 和 Loop 层），就是这张组织图能转起来的地基。"]]],["p",{"uuid":"ms64fy2mjovw3bwuzs"},["span",{"data-type":"text"},["span",{"sz":11,"szUnit":"pt","data-type":"leaf"},"单点 Agent 的高可用是整张图能运转的前提。先做扎实单点，再连点成图。"]]],["p",{"uuid":"ms64fyfgego97q9fp2u"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]]],["h2",{"uuid":"ztfvd9u7fozi8s1ei1su","spacing":{"before":21.333333333333332,"after":12,"line":0.8529411764705882}},["span",{"data-type":"text"},["span",{"bold":true,"sz":16,"szUnit":"pt","data-type":"leaf"},"实验：检查一份需要核实的会议纪要初稿"]]],["hr",{"color":"#D8D8D8","width":"100%","sz":1,"id":"m0uoo7"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"bold":true,"data-type":"leaf"},"实验目标"],["span",{"data-type":"leaf"},"：用另一种发布材料走一遍“留过程记录 → 按自检清单检查 → 修订 → 整理下次可用的检查项”的流程。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"bold":true,"data-type":"leaf"},"准备材料"],["span",{"data-type":"leaf"},"："]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"下载并解压"]],["a",{"href":"https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20260515/jzdxbd/%E8%AF%BE%E6%97%B68-%E4%BC%9A%E8%AE%AE%E7%BA%AA%E8%A6%81%E8%87%AA%E6%A3%80%E7%BB%83%E4%B9%A0.zip"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"会议纪要自检练习文件包"]]],["span",{"data-type":"text"},["span",{"data-type":"leaf"},"。解压后会得到一个 "],["span",{"code":{"value":true},"data-type":"leaf"},"lesson8_minutes_check"],["span",{"data-type":"leaf"}," 文件夹，里面有 6 个 Markdown 文件（以 "],["span",{"code":{"value":true},"data-type":"leaf"},".md"],["span",{"data-type":"leaf"}," 结尾的纯文本文件）："]]],["p",{"spacing":{"line":1.15,"lineRule":"auto"},"list":{"listId":"in37f7edaecv","level":0,"isOrdered":false,"isTaskList":false,"listStyleType":"SARR_SDIO_SCIR","symbolStyle":{},"listStyle":{"format":"bullet","text":"➔","align":"left"},"hideSymbol":false}},["span",{"data-type":"text"},["span",{"code":{"value":true},"data-type":"leaf"},"minutes_draft.md"],["span",{"data-type":"leaf"},"：已经生成好的会议纪要初稿，里面故意包含把没完成的事项写成已确认、遗漏阻塞事项和占位敏感项问题。"]]],["p",{"spacing":{"line":1.15,"lineRule":"auto"},"list":{"listId":"in37f7edaecv","level":0,"isOrdered":false,"isTaskList":false,"listStyleType":"SARR_SDIO_SCIR","symbolStyle":{},"listStyle":{"format":"bullet","text":"➔","align":"left"},"hideSymbol":false}},["span",{"data-type":"text"},["span",{"code":{"value":true},"data-type":"leaf"},"work_items.md"],["span",{"data-type":"leaf"},"：任务记录，用来核对事项状态。"]]],["p",{"spacing":{"line":1.15,"lineRule":"auto"},"list":{"listId":"in37f7edaecv","level":0,"isOrdered":false,"isTaskList":false,"listStyleType":"SARR_SDIO_SCIR","symbolStyle":{},"listStyle":{"format":"bullet","text":"➔","align":"left"},"hideSymbol":false}},["span",{"data-type":"text"},["span",{"code":{"value":true},"data-type":"leaf"},"feedback_summary.md"],["span",{"data-type":"leaf"},"：客户反馈摘要，用来核对回访数量和反馈内容。"]]],["p",{"spacing":{"line":1.15,"lineRule":"auto"},"list":{"listId":"in37f7edaecv","level":0,"isOrdered":false,"isTaskList":false,"listStyleType":"SARR_SDIO_SCIR","symbolStyle":{},"listStyle":{"format":"bullet","text":"➔","align":"left"},"hideSymbol":false}},["span",{"data-type":"text"},["span",{"code":{"value":true},"data-type":"leaf"},"meeting_notes.md"],["span",{"data-type":"leaf"},"：回访排期记录，用来核对已确认和待回复客户。"]]],["p",{"spacing":{"line":1.15,"lineRule":"auto"},"list":{"listId":"in37f7edaecv","level":0,"isOrdered":false,"isTaskList":false,"listStyleType":"SARR_SDIO_SCIR","symbolStyle":{},"listStyle":{"format":"bullet","text":"➔","align":"left"},"hideSymbol":false}},["span",{"data-type":"text"},["span",{"code":{"value":true},"data-type":"leaf"},"approval_notes.md"],["span",{"data-type":"leaf"},"：审批记录，用来核对投诉处理方案是否可以对外发送。"]]],["p",{"spacing":{"line":1.15,"lineRule":"auto"},"list":{"listId":"in37f7edaecv","level":0,"isOrdered":false,"isTaskList":false,"listStyleType":"SARR_SDIO_SCIR","symbolStyle":{},"listStyle":{"format":"bullet","text":"➔","align":"left"},"hideSymbol":false}},["span",{"data-type":"text"},["span",{"code":{"value":true},"data-type":"leaf"},"private_notes.md"],["span",{"data-type":"leaf"},"：占位私密备注，用来测试敏感信息过滤。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"bold":true,"data-type":"leaf"},"操作"],["span",{"data-type":"leaf"},"："]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"把这些文件放进同一个测试文件夹。使用千问办公时，新建任务，点击“选择工作目录”，选择这个文件夹；看到输入框下方出现文件夹名后，粘贴提示词运行。如果使用其他 Agent，就上传这些文件，或选择这个测试文件夹作为可读取目录。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"先让 Agent 读初稿，不急着修订："]]],["code",{"syntax":"plaintext","theme":"default","uuid":"98nfwsz6lx98oc0094mz","language":"text-x-markdown"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"请先阅读 minutes_draft.md，列出最需要核实的 3 条说法。暂时不要修订。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"看一下它列出的 3 条：如果都是“已经完成、已经确认、已经通过”这类说法，通常就需要回到其他文件找证据。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"如果它只挑了格式问题，没有挑出需要证据支持的说法，可以提醒它优先找“已完成、已确认、已通过”这类说法。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"接着让它按证据检查并修订。如果你希望便于检查，可以在提示词最后加一句："],["span",{"code":{"value":true},"data-type":"leaf"},"请把完整结果写入当前文件夹的 lesson8_result.md。"]]],["code",{"syntax":"text/x-markdown","theme":"default","uuid":"jowlr3dy91m0tayf3e0g","language":"text-x-markdown","wrap":true},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"请检查并修订 minutes_draft.md 这份会议纪要初稿。\n对照同一文件夹里的 work_items.md、feedback_summary.md、meeting_notes.md、approval_notes.md 和 private_notes.md：\n- 凡是写成“已确认、已通过、已完成”的内容都必须有证据；\n- 进行中、阻塞、待确认不能写成已确认；\n- 不能遗漏阻塞事项；\n- private_notes.md 的具体内容不得出现在会议纪要正文、问题清单、过程记录、自检结果等任何输出中，只能写“已发现并过滤敏感信息”。\n请输出：问题清单、修订版会议纪要、过程记录、自检结果、下次可用的检查项、仍需我确认的事项。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"结果出来后，先看问题清单，再看修订版。重点检查这四处："]]],["p",{"spacing":{"line":1.15,"lineRule":"auto"},"list":{"listId":"j6id28ihcoi4","level":0,"isOrdered":false,"isTaskList":false,"listStyleType":"SARR_SDIO_SCIR","symbolStyle":{},"listStyle":{"format":"bullet","text":"➔","align":"left"},"hideSymbol":false}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"它有没有把“5 家重点客户已经全部完成回访”改成 3 家已完成、2 家待联系；"]]],["p",{"spacing":{"line":1.15,"lineRule":"auto"},"list":{"listId":"j6id28ihcoi4","level":0,"isOrdered":false,"isTaskList":false,"listStyleType":"SARR_SDIO_SCIR","symbolStyle":{},"listStyle":{"format":"bullet","text":"➔","align":"left"},"hideSymbol":false}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"它有没有把“所有客户确认时间”改成部分确认、部分待回复；"]]],["p",{"spacing":{"line":1.15,"lineRule":"auto"},"list":{"listId":"j6id28ihcoi4","level":0,"isOrdered":false,"isTaskList":false,"listStyleType":"SARR_SDIO_SCIR","symbolStyle":{},"listStyle":{"format":"bullet","text":"➔","align":"left"},"hideSymbol":false}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"它有没有把“投诉处理方案已通过审核”改成风险/阻塞；"]]],["p",{"spacing":{"line":1.15,"lineRule":"auto"},"list":{"listId":"j6id28ihcoi4","level":0,"isOrdered":false,"isTaskList":false,"listStyleType":"SARR_SDIO_SCIR","symbolStyle":{},"listStyle":{"format":"bullet","text":"➔","align":"left"},"hideSymbol":false}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"它有没有删除占位敏感项，并且没有在自检说明里复述具体内容。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"再看“下次可用的检查项”：它有没有把这次的具体问题，改写成下次处理同类材料也能使用的问题。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"如果它没有给出自检结果，再追加一轮："]]],["code",{"syntax":"text/x-markdown","theme":"default","uuid":"kqh0krg8y2yelrhazhzd","language":"plaintext","wrap":true},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"请再按下面的自检清单检查一遍，并修订刚才的输出：\n1. 每条写成“已确认、已通过、已完成”的内容是否有证据；\n2. 是否有未完成事项被写成已确认；\n3. 是否遗漏阻塞事项；\n4. 是否把计划、讨论或承诺误写成结果；\n5. 是否泄露或复述不能对外发送的信息。\n如果发现问题，请先修订，再补充下次可用的检查项，然后输出自检结果。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"最后再做一次人工检查：在输出里搜索 "],["span",{"code":{"value":true},"data-type":"leaf"},"某手机号"],["span",{"data-type":"leaf"},"、"],["span",{"code":{"value":true},"data-type":"leaf"},"某预算金额"],["span",{"data-type":"leaf"},"、"],["span",{"code":{"value":true},"data-type":"leaf"},"某个人评价"],["span",{"data-type":"leaf"},"。如果练习文件里用了其他占位符，也要搜索对应内容。如果这些内容出现在问题清单、过程记录、自检结果或修订说明里，用这句要求重新修订："]]],["code",{"syntax":"text/x-markdown","theme":"default","uuid":"pn9z20i53sz07d9lzxa6","language":"text-x-markdown","wrap":true},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"敏感信息不能出现在任何输出中。问题清单、过程记录、自检结果、修订说明和最终内容里都只能写“已发现并过滤敏感信息”，不得复述原文、金额、手机号、个人评价或其他具体内容。请重新修订并自检。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"如果你还发现别的问题，不要只在这次输出里改掉。把它改写成一句下次能直接使用的检查项。例如，不写“这次把 5 家客户都写成已完成”，而写："],["span",{"code":{"value":true},"data-type":"leaf"},"是否把待联系、待回复、待审批的事项写成已完成或已确认？"],["span",{"data-type":"leaf"}," 以后处理类似材料时，把这句放进自检清单。"]]],["h2",{"uuid":"zk5zjuoen021muvcgnpb","spacing":{"before":21.333333333333332,"after":12,"line":0.8529411764705882}},["span",{"data-type":"text"},["span",{"bold":true,"sz":16,"szUnit":"pt","data-type":"leaf"},"✅ 本节小结"]]],["hr",{"color":"#D8D8D8","width":"100%","sz":1,"id":"2hh72a"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"下次处理日报、周报、会议纪要时，不要只让 Agent 生成正文。先给执行规则，要求它留下过程记录，再换个对话按清单检查。发现问题后，修这次输出，也把问题补进执行规则或自检清单。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"把“生成、检查、修订、再检查”固定下来，下一次就不必由你一轮一轮催着 Agent 做。整理、摘要、草稿、待确认清单这类低风险步骤，可以逐步交给 Agent 按流程自动完成。"]]],["p",{"blockquote":false,"ind":{},"spacing":{}},["span",{"data-type":"text"},["span",{"bold":true,"data-type":"leaf"},"非必要不上图"],["span",{"data-type":"leaf"},"。只有涉及多角色协作与长周期审批时才用图编排；绝大多数场景，做扎实单 Agent 的自检闭环就够了。"]]],["p",{"ind":{"left":0},"spacing":{"line":1},"blockquote":true},["span",{"data-type":"text"},["span",{"bold":true,"data-type":"leaf"},"注意"],["span",{"data-type":"leaf"},"：发送、删除、付款、外发敏感信息这类高风险动作，仍然要等人确认。"]]],["h2",{"uuid":"5veilcivty9eptrwp8if","spacing":{"before":21.333333333333332,"after":12,"line":0.8529411764705882}},["span",{"data-type":"text"},["span",{"bold":true,"sz":16,"szUnit":"pt","data-type":"leaf"},"✅ 评价反馈"]]],["hr",{"color":"#D8D8D8","width":"100%","sz":1,"id":"1t49fu"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},""]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"欢迎你参与"]],["a",{"href":"https://survey.aliyun.com/apps/zhiliao/ww0sx2B5r"},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"阿里云大模型ACA课程调查问卷"]]],["span",{"data-type":"text"},["span",{"data-type":"leaf"},"反馈学习体验和课程评价。"]]],["p",{"ind":{"left":0},"spacing":{"line":1}},["span",{"data-type":"text"},["span",{"data-type":"leaf"},"你的批评和鼓励都是我们前进的动力！"]]]]
