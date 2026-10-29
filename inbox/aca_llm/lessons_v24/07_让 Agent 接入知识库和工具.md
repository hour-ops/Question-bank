# 课时7：让 Agent 接入知识库和工具

> 来源：edu.aliyun.com/course/3126500/lesson/344730479

## 🚄 前言

上一节你已经体验过：把一堆散乱材料扔进文件夹，Agent 带着你的问题去翻这些文件——搜关键词、读内容、觉得信息不够就换个角度继续找，最后把找到的东西整理成报告。

但做完以后你可能会想：那些材料都是我自己攒的，本来就在电脑上。要是我手上没有现成资料呢？要是信息在网上、在别人的文章里、在一堆网页里呢？

这节课解决两个问题：资料不在手边时，怎么让 Agent 自己去找；以及 Agent 目前做不到的事，怎么给它补上新能力。

## ✏️ 课程目标

学完本课程后，你将能够：

- 让 Agent 联网搜索、抓取网页、读取钉钉等平台记录，把散落各处的信息整理成本地资料。

- 给 Agent 接入一个 MCP 工具，完成一次带真实数据的工具调用。

- 判断当前接入的工具是否过多，并关掉用不上的 MCP。

## 1 手上没有现成资料怎么办

比如你打算去三亚度假，想找当地攻略、查酒店评价、看景点推荐。以前你得自己打开马蜂窝、小红书、携程，一个个搜，一篇篇看，把有用的信息复制下来，再自己整理。

现在可以让桌面 Agent 替你做这件事。

### 1.1 让 Agent 去网上找资料

在千问办公里输入：

帮我搜索三亚亲子度假攻略，找几篇当地游玩推荐和亲子酒店评价，把搜到的信息整理好，保存到"三亚调研"文件夹里。
你会看到 Agent 开始工作：先联网搜索，再逐个打开相关网页，提取里面的正文内容，保存为本地文件。几分钟后，文件夹里就多了一份整理好的调研报告——景点、酒店、行程建议都按主题归好了类，不是你一篇篇复制粘贴的，是 Agent 自己跑出来的。

有时候你不需要搜索，已经知道要看哪个网页——比如同事发来一篇产品文档的链接。直接把链接给 Agent，让它抓取内容并保存：

把这个网页的内容抓取下来，保存到本地文件：
https://help.aliyun.com/zh/model-studio/what-is-model-studio
搜几篇攻略、抓几个网页，对于简单的信息收集已经够用了。但如果你要深入研究一个问题——比如调研一个行业的市场现状——几篇文章往往不够，需要多轮搜索、交叉验证不同来源的信息。很多桌面 Agent 提供了"深入研究"功能，你给一个问题，它会自动完成这个过程，最后整理成一份完整的研究报告。对于千问办公，可以在技能市场里搜索“深入研究”或“深度研究”相关skill来使用。关于技能（Skill）的概念和用法，会在后续课程中详细讲解。

### 1.2 你自己的资料散在各个平台里

上面找的是公开信息——网上搜得到的攻略、文章、文档。但还有一类资料，是你自己产生的：钉钉里的聊天记录、会议纪要、项目文档、语雀知识库里的笔记。这些东西搜索引擎搜不到，它们在你自己的账号里。

举一个常见的例子：写周报。有人会问，让 Agent 帮我写周报，它怎么知道我这周做了什么？难道我所有工作都是通过它完成的？

当然不是。但你的工作痕迹并没有消失——它们散落在你每天都在用的工具里：钉钉群聊里讨论了什么、会议纪要写了什么、项目文档改了哪些、日程安排了几场评审。你不需要特意整理，这些记录本来就在那里，只是你自己写周报时懒得一个个去翻。

这些平台可以通过工具接入，让 Agent 直接读取里面的内容，不需要你手动导出。以钉钉为例，千问办公已经内置了钉钉连接器。在千问办公左侧选择 扩展 → 连接器（不同版本入口可能不同，也可能在 设置 →连接器与 MCP），开启钉钉连接器即可。开启后，Agent 就能直接查你的钉钉消息、文档和会议记录：

帮我写本周周报。去钉钉查看我参与的记录：群聊里@我和我发的消息、我的单聊消息、我的会议纪要、我创建或编辑的文档。
Agent 会自己去翻你这周的群聊讨论、会议纪要、文档更新，拼出一份初稿。你看一遍，改改措辞就能交。费时间的从来不是"写"这个动作，而是"回忆和整理"——这一步交给 Agent 来做。

当然不止周报，任何需要从钉钉里查资料的场景都可以：

帮我看一下钉钉文档里"产品需求"文件夹的内容，把最近更新的需求整理成一份清单。
对于语雀、Notion 等其他平台，也有对应的工具可以接入。这些工具通常通过 MCP 的方式接入——MCP 是什么、怎么安装配置，第 3 节会详细介绍。

Agent 从网上搜回来的内容，保存时默认就是 Markdown 或纯文本，不需要你操心格式。但你自己手上可能还有一些现成的资料想放进来——同事发的 Word 文档、下载的 PDF 报告、导出的 Excel 表格。Agent 可以读取这些格式，日常临时查看没有问题。但如果这些资料需要长期保存、反复检索、频繁引用，建议让 Agent 把核心内容转成 Markdown（.md 文件）。不是因为其他格式不能读，而是 Markdown 更适合作为长期知识库格式——它是纯文本，结构清楚，搜索和版本管理方便，也不依赖特定软件或复杂的解析过程。相比之下，PDF、Word 等格式在复杂排版、扫描件、表格、分页等情况下，可能出现内容顺序错乱、遗漏或噪音过多的问题。原始文件可以继续保留，Markdown 作为日常让 Agent 查阅和复用的整理版。

### 1.3 Agent 查本地文件时在做什么

到这里，不管是从网上搜的、从平台接入的、还是你自己手上的资料，都可以汇集到本地文件夹里。你问 Agent 一个问题，它翻了好几份文件就给出了回答。但它是怎么找到相关内容的？是把所有文件都读一遍吗？

并不是。拿上一节的项目文件夹举例：里面有备忘录、活动方案、报名数据、沟通记录等十来份文件。你问"场地费用有没有超预算"，Agent 不会把所有文件都读一遍。它会同时用好几个词去搜——"场地费用""报价""预算""金额"——因为不同文件里对同一件事的叫法可能不一样。报价单里写的是"场地租赁费"，活动方案里写的是"预算明细"，备忘录里写的是"场地那边报价"。用一个词只能找到一部分，多个词一起搜才能把信息找全。搜到之后，它还要判断：方案改过两版、预算数字不一样，于是又去翻备忘录确认最终用的是哪一版。几轮下来，它把散在不同文件里的信息拼起来，告诉你费用比最终预算超了多少。

整个过程是 Agent 在推理和判断——搜什么、读到的够不够、要不要换个方向再找——不是按固定流程机械匹配。这种做法叫 Agentic RAG——不需要提前建索引，Agent 自己去检索、去判断、去拼信息。

你自己在个人电脑上用，这套做法完全够。但如果要对外提供 AI 问答服务——比如客服机器人、产品帮助中心——很多人同时提问、还要求秒级响应，每次都让 Agent 从头搜一遍文件就太慢了。这时候就需要提前把资料切片、建好索引，用户一提问就能快速匹配到相关内容。这就是前面 RAG 章节讲的做法。

回头看一下这一节，Agent 搜了网页、打开了链接、抓取了正文、读取了钉钉记录、保存成了文件。但大模型本身不能上网，不能打开文件，更不能读取钉钉。它怎么做到这些事的？

## 2 Agent 的能力从哪来

答案是：大模型只负责决定做什么，真正执行的是外部工具。

你说"帮我搜三亚攻略"，大模型判断这个任务需要搜索工具，于是发出一条指令：调用搜索服务，关键词=三亚亲子攻略。搜索引擎返回结果后，大模型再判断哪些链接值得打开，于是又发出指令：调用网页抓取工具，地址=某个链接。大模型并没有上网，它做的是决定调用哪个工具、传什么参数。

画图也是一样。你说"帮我画一张日出的图"，大模型判断需要图像生成工具，发出指令：调用图像生成服务，内容=日出。图片是专门的图像生成服务画的，不是大模型画的。

搜网页、读文件、画图、查天气，背后都是同一个流程：

- 你提出需求

- 大模型判断需要哪个工具，生成一条工具调用指令

- 千问办公拿着指令去调用对应的外部服务

- 服务返回结果，大模型再根据结果组织回答

所以前面你看到的那些操作——联网搜索、打开网页抓取内容、生成文件并保存到文件夹、画图——每一步都是大模型在调用工具。Agent 的能力是两方配合的结果：大模型决定做什么，工具负责真正去做。Agent 能做多少事，取决于它能调用多少工具。

千问办公预装了一批常用工具（读写文件、执行代码、联网搜索、操作浏览器等），所以前面的任务不需要你额外配置。但有些能力它没有预装——比如查实时路况、规划驾车路线。没有地图工具时，Agent 只能搜网页凑一个模糊答案。怎么给它装上新工具？

## 3 MCP：给 Agent 接入工具

接入工具的方式不止一种，MCP（Model Context Protocol）是目前被广泛采用的一种。它的好处是：同一个工具，装到千问办公能用，装到 Claude Code、OpenClaw 这些 AI 助手上也能用，不用重新开发。

### 3.1 给千问办公装上高德地图

假设周末你想带家人去杭州几个景点玩一天，最后到杭州东站坐高铁回家，想让 Agent 帮你规划一条最省时间的驾车路线。在没有地图工具时，Agent 费了很大劲，搜了二十多次网页，最后只能给你一个”大约 20 到 35 分钟”的模糊回答。现在给它装上高德地图，看看有什么不同。

- 打开百炼 Amap Maps 高德地图 MCP 页面并登录，点击立即开通。弹窗里的 AMAP_MAPS_API_KEY 不填，直接点击确认开通。

- 开通后点击页面上的 API Key，复制一个百炼 API Key。

- 回到千问办公，在左侧选择 扩展 > 连接器（不同版本入口可能不同，也可能在 设置 >连接器与 MCP），再点击添加 > 粘贴 JSON 配置，粘贴下面这段配置，把 ${DASHSCOPE_API_KEY} 替换成刚复制的 API Key，然后点击导入。

{
 "mcpServers": {
 "AliyunBailianMCP_amap-maps": {
 "url": "https://dashscope.aliyuncs.com/api/v1/mcps/amap-maps/mcp",
 "headers": {
 "Authorization": "Bearer ${DASHSCOPE_API_KEY}"
 }
 }
 }
}

- 配置完成后，回到对话界面，再问同样的问题：“帮我规划一条驾车路线，从西湖出发，去灵隐寺和西溪湿地，最后到杭州东站，时间最短。”

Agent 调用高德地图的地理编码和路线规划接口，先查出各地点的坐标，再分别计算不同访问顺序下各段路程的驾车时间，比较后给出一条总用时最短的路线，精确到每段路程的预估时间和距离。

装上高德地图之后，Agent 就能规划带有具体数据的驾车路线了。

停下来看一下运行过程：你会看到 Agent 不是只调了一次工具，而是先把地点名称转成坐标、再对不同的访问顺序分别计算驾车时间、最后比较总用时选出最优方案——同一个 MCP 里有多个工具，Agent 会按任务需要自己安排调用顺序和次数。

### 3.2 为什么你不用教 Agent 怎么用工具

回想一下，你刚才并没有告诉千问办公"高德地图能做什么、怎么调用、返回什么格式"。你只是按页面提示粘贴了配置和 Key，剩下的事 Agent 自己就处理好了。

它怎么知道该怎么用的？因为高德地图 MCP Server 自带了一份工具描述——告诉 AI 自己叫什么、能做什么、需要什么参数。千问办公连上它的那一刻，就自动拿到了这份描述。你没看到，但 Agent 看到了。它大概长这样：

工具名称：maps_direction
功能说明：根据起点和终点规划驾车路线，返回距离、预计时间和途经道路。
需要参数：
 - origin：起点（如"西湖"）
 - destination：终点（如"杭州东站"）
工具名称：maps_search_nearby
功能说明：搜索某个地点附近的餐厅、酒店、加油站等。
需要参数：
 - location：中心位置（如"西湖"）
 - keyword：要搜什么（如"浙菜餐厅"）
这只是高德地图 MCP 里的两个工具，它实际上还带了地点搜索、实时路况等好几个。每个工具都有名字、功能说明和需要什么参数——Agent 看到这些，就知道什么时候该调哪个、传什么值。

你什么都不用定义，工具自己会说话——MCP 要求每个工具都带上自己的描述，Agent 连上就能读到。

### 3.3 去哪里找更多 MCP 工具？

下次遇到 Agent 做不了的事——查天气、管日历、连数据库——去 MCP 市场搜一下，大概率有人做好了：

- 百炼 MCP 广场（阿里云百炼平台）——覆盖地图、天气、搜索、文档处理等常见场景，选中后按提示配置即可使用。

- ModelScope 魔搭社区 MCP 广场——社区里开发者自己做的 MCP 工具，覆盖场景更广。

## 4 工具不是越多越好

MCP 市场里有上万个工具，接入又方便。是不是应该把能找到的都装上，装得越多 Agent 越强？

恰恰相反。工具越多，Agent 反而可能变笨。而且工具本身靠不靠谱、安全不安全，都直接影响使用效果。要理解为什么，得先知道大模型的工作空间是怎么回事。

### 4.1 对话越长，桌面越挤

大模型的上下文窗口就像一张办公桌——你的问题、工具清单、之前的对话记录全都堆在上面，总空间有限。

用实际数字来感受一下。上下文窗口的计量单位叫 token（一个汉字大约是 1 到 2 个 token）。假设一个模型的上下文窗口是 128000 token（约 12 万字，目前主流模型的水平），然后对话开始：读一份合同 1 万 token、分析一份 Excel 5000 token、几次工具调用的输入输出再几千 token，加上 Agent 每轮的思考和回复，看似很大的 12 万 token 空间，几十轮对话堆下来也会填满。

数字不用记，记住一点就够：上下文窗口是有限的，每一轮对话都在消耗它。

### 4.2 工具描述也在占空间

对话过程中桌面会越来越满，这你已经知道了。但还有一件事你可能没意识到：在你开口之前，桌面就已经不是空的了。

还记得前面讲的工具描述吗？每个工具的“自我介绍”都要放进上下文，Agent 才知道自己能用什么。千问办公预装的几个内置工具，描述加起来还不太占地方。但如果你装了高德地图 MCP、日历 MCP、邮件 MCP、数据库 MCP、新闻 MCP，每个 MCP 都有自己的工具说明，有些 MCP 还提供好几个工具。

这就涉及到 MCP 的一个特点：每添加一个 MCP Server，它的所有工具描述都要写进上下文。而且很多 MCP Server 不只提供一个工具。比如高德地图 MCP 可能包含“路线规划”“地点搜索”“实时路况”等多个工具，一个 Server 就带来好几条工具描述。你装了 5 个 MCP Server，上下文里可能一下子多出二三十条工具描述。

可以做一个测试：问 Agent “请把你现在能调用的所有工具列出来，每个工具叫什么、用来做什么、工具描述大概多少字，最后告诉我加起来一共多少字。”你会看到一份比预期长得多的清单——你以为装了几个 MCP，实际是几十个工具，工具描述加起来可能一两万字。

工具描述越多，留给对话内容的空间就越少。所以用不上的 MCP 先关掉，不相关的话题开新对话窗口，效果往往比硬撑一个长对话要好。

### 4.3 装 MCP 就是在扩大 Agent 的权限

装 MCP 就是给 Agent 开权限。本地 MCP 能读写你电脑上的文件，如果授权范围过大，Agent 可能误改甚至误删你的文件。远程 MCP 会把你的对话内容发到外部服务器，来路不明的 Server 可能截获你的信息——已有公开案例，某个社区邮件 MCP 被发现偷偷转发用户邮件，影响了数百家机构。更隐蔽的风险是，恶意 MCP 可以在工具描述里藏入隐藏指令，引导 Agent 做出你没要求的操作。

安装或开启 MCP 前，先确认来源是否可信、它要什么权限、是否需要 API Key 或账号授权。日常使用时，记住三条做法：

- 只从百炼 MCP 广场、魔搭社区等经过平台审核的渠道安装

- 本地 MCP 只开放当前任务需要的文件夹或数据库

- 用完之后，用不到的 MCP 先关掉

## 动手实验

### 实验 1：让 Agent 查一个资料文件夹

- 准备一个文件夹，放入 5 到 10 份你真实会用的资料，例如会议纪要、旅行攻略、产品说明、项目文档。

- 混入一份和问题无关的资料，观察 Agent 会不会被带偏。

- 提出一个需要综合多份资料才能回答的问题，并要求 Agent 在回答中标注每条信息来自哪个文件。

- 检查它标注的文件是否真实存在、引用是否准确，回答中是否有无法追溯来源的信息。

- 对现有资料没写明的信息，观察它是否明确说明，而不是直接猜。

### 实验 2：在你关心的场景里跑一次工具协同

- 选择一个需要外部工具的任务，例如路线规划、天气查询、日历安排或业务资料查询。

- 确认当前 Agent 是否已经接入对应 MCP 或工具。

- 发起一个真实问题，观察运行过程中是否出现工具名、参数和返回结果。

- 对比“未调用工具的文字建议”和“调用工具后的真实结果”有什么差异。

- 关闭不相关工具，再运行一次，观察工具列表变短后是否更容易判断。

## ✅ 本节小结

这节课从"资料不在手边"出发，让 Agent 自己去网上找、从平台里取，再到给它装上新工具获取实时数据。背后是同一个逻辑：大模型负责判断做什么，工具负责真正去做。

## ✅ 评价反馈

欢迎你参与阿里云大模型ACA课程调查问卷反馈学习体验和课程评价。

你的批评和鼓励都是我们前进的动力！

eyJ2IjoxLCJqdGkiOiI1ZDViMzZjYTBhZjI0MzZlYjc5OWVlNTgwNmZkZDU3OCIsImxpZCI6MzQ0NzMwNDc5LCJjaWQiOjMxMjY1MDAsInVpZCI6MTQ3MzUzNjI0MjM2MTM2NywiZXhwIjoxNzkxNzM2MTAxfQ.E0Ei-sZIrOD53OnXXIoloI5kxRZKkVddFcYUDw_P1U8

["root", {}, ["h2", {"uuid": "50qcpxbxc9ivf8ubto86", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "🚄 前言"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "4lqrm3"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "上一节你已经体验过：把一堆散乱材料扔进文件夹，Agent 带着你的问题去翻这些文件——搜关键词、读内容、觉得信息不够就换个角度继续找，最后把找到的东西整理成报告。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "但做完以后你可能会想：那些材料都是我自己攒的，本来就在电脑上。要是我手上没有现成资料呢？要是信息在网上、在别人的文章里、在一堆网页里呢？"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "这节课解决两个问题：资料不在手边时，怎么让 Agent 自己去找；以及 Agent 目前做不到的事，怎么给它补上新能力。"]]], ["h2", {"uuid": "750txiuy250kgayqtrnj", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "✏️ 课程目标"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "6767yj"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "学完本课程后，你将能够："]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "upah0qiwx9pf", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "让 Agent 联网搜索、抓取网页、读取钉钉等平台记录，把散落各处的信息整理成本地资料。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "upah0qiwx9pf", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "给 Agent 接入一个 MCP 工具，完成一次带真实数据的工具调用。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "upah0qiwx9pf", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "判断当前接入的工具是否过多，并关掉用不上的 MCP。"]]], ["h2", {"uuid": "82qvq5s9b33kt0whobir", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "1 手上没有现成资料怎么办"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "7tn4f1"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "比如你打算去三亚度假，想找当地攻略、查酒店评价、看景点推荐。以前你得自己打开马蜂窝、小红书、携程，一个个搜，一篇篇看，把有用的信息复制下来，再自己整理。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "现在可以让桌面 Agent 替你做这件事。"]]], ["h3", {"uuid": "v6zg9spe4jzkcioxfhc6"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "1.1 让 Agent 去网上找资料"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "在千问办公里输入："]]], ["code", {"uuid": "tv5jlrqa2s44mpyg36pc", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "帮我搜索三亚亲子度假攻略，找几篇当地游玩推荐和亲子酒店评价，把搜到的信息整理好，保存到\"三亚调研\"文件夹里。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "你会看到 Agent 开始工作：先联网搜索，再逐个打开相关网页，提取里面的正文内容，保存为本地文件。几分钟后，文件夹里就多了一份整理好的调研报告——景点、酒店、行程建议都按主题归好了类，不是你一篇篇复制粘贴的，是 Agent 自己跑出来的。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["img", {"id": "v8q1of", "src": "https://scms-prod-sh-public.oss-cn-shanghai.aliyuncs.com/course_picture/teewauldmiptdrsftxrw.png", "width": 936, "height": 318}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "有时候你不需要搜索，已经知道要看哪个网页——比如同事发来一篇产品文档的链接。直接把链接给 Agent，让它抓取内容并保存："]]], ["code", {"uuid": "eto9toloex4g2076wpu3", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "把这个网页的内容抓取下来，保存到本地文件：\nhttps://help.aliyun.com/zh/model-studio/what-is-model-studio"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "搜几篇攻略、抓几个网页，对于简单的信息收集已经够用了。但如果你要深入研究一个问题——比如调研一个行业的市场现状——几篇文章往往不够，需要多轮搜索、交叉验证不同来源的信息。很多桌面 Agent 提供了\"深入研究\"功能，你给一个问题，它会自动完成这个过程，最后整理成一份完整的研究报告。对于千问办公，可以在技能市场里搜索“深入研究”或“深度研究”相关skill来使用。关于技能（Skill）的概念和用法，会在后续课程中详细讲解。"]]], ["h3", {"uuid": "v1t1bdfr79zz97khuowz"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "1.2 你自己的资料散在各个平台里"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "上面找的是公开信息——网上搜得到的攻略、文章、文档。但还有一类资料，是你自己产生的：钉钉里的聊天记录、会议纪要、项目文档、语雀知识库里的笔记。这些东西搜索引擎搜不到，它们在你自己的账号里。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "举一个常见的例子：写周报。有人会问，让 Agent 帮我写周报，它怎么知道我这周做了什么？难道我所有工作都是通过它完成的？"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "当然不是。但你的工作痕迹并没有消失——它们散落在你每天都在用的工具里：钉钉群聊里讨论了什么、会议纪要写了什么、项目文档改了哪些、日程安排了几场评审。你不需要特意整理，这些记录本来就在那里，只是你自己写周报时懒得一个个去翻。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "这些平台可以通过工具接入，让 Agent 直接读取里面的内容，不需要你手动导出。以钉钉为例，千问办公已经内置了钉钉连接器。在千问办公左侧选择 扩展 → 连接器（不同版本入口可能不同，也可能在 设置 →连接器与 MCP），开启钉钉连接器即可。开启后，Agent 就能直接查你的钉钉消息、文档和会议记录："]]], ["code", {"uuid": "hw55e9n7oi5k7hzqzfkg", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "帮我写本周周报。去钉钉查看我参与的记录：群聊里@我和我发的消息、我的单聊消息、我的会议纪要、我创建或编辑的文档。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "Agent 会自己去翻你这周的群聊讨论、会议纪要、文档更新，拼出一份初稿。你看一遍，改改措辞就能交。费时间的从来不是\"写\"这个动作，而是\"回忆和整理\"——这一步交给 Agent 来做。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "当然不止周报，任何需要从钉钉里查资料的场景都可以："]]], ["code", {"uuid": "cozxns3bff2as5we8k3q", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "帮我看一下钉钉文档里\"产品需求\"文件夹的内容，把最近更新的需求整理成一份清单。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "对于语雀、Notion 等其他平台，也有对应的工具可以接入。这些工具通常通过 MCP 的方式接入——MCP 是什么、怎么安装配置，第 3 节会详细介绍。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["img", {"id": "m7q6hi", "src": "https://scms-prod-sh-public.oss-cn-shanghai.aliyuncs.com/course_picture/alxgcigrtvprbzrceain.png", "width": 936, "height": 318}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "Agent 从网上搜回来的内容，保存时默认就是 Markdown 或纯文本，不需要你操心格式。但你自己手上可能还有一些现成的资料想放进来——同事发的 Word 文档、下载的 PDF 报告、导出的 Excel 表格。Agent 可以读取这些格式，日常临时查看没有问题。但如果这些资料需要长期保存、反复检索、频繁引用，建议让 Agent 把核心内容转成 Markdown（.md 文件）。不是因为其他格式不能读，而是 Markdown 更适合作为长期知识库格式——它是纯文本，结构清楚，搜索和版本管理方便，也不依赖特定软件或复杂的解析过程。相比之下，PDF、Word 等格式在复杂排版、扫描件、表格、分页等情况下，可能出现内容顺序错乱、遗漏或噪音过多的问题。原始文件可以继续保留，Markdown 作为日常让 Agent 查阅和复用的整理版。"]]], ["h3", {"uuid": "bcubce85qtwcl5l2pmw4"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "1.3 Agent 查本地文件时在做什么"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "到这里，不管是从网上搜的、从平台接入的、还是你自己手上的资料，都可以汇集到本地文件夹里。你问 Agent 一个问题，它翻了好几份文件就给出了回答。但它是怎么找到相关内容的？是把所有文件都读一遍吗？"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "并不是。拿上一节的项目文件夹举例：里面有备忘录、活动方案、报名数据、沟通记录等十来份文件。你问\"场地费用有没有超预算\"，Agent 不会把所有文件都读一遍。它会同时用好几个词去搜——\"场地费用\"\"报价\"\"预算\"\"金额\"——因为不同文件里对同一件事的叫法可能不一样。报价单里写的是\"场地租赁费\"，活动方案里写的是\"预算明细\"，备忘录里写的是\"场地那边报价\"。用一个词只能找到一部分，多个词一起搜才能把信息找全。搜到之后，它还要判断：方案改过两版、预算数字不一样，于是又去翻备忘录确认最终用的是哪一版。几轮下来，它把散在不同文件里的信息拼起来，告诉你费用比最终预算超了多少。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["img", {"id": "cjizcm", "src": "https://scms-prod-sh-public.oss-cn-shanghai.aliyuncs.com/course_picture/lhsvkhtxxtxmlsqukzne.png", "width": 936, "height": 318}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "整个过程是 Agent 在推理和判断——搜什么、读到的够不够、要不要换个方向再找——不是按固定流程机械匹配。这种做法叫 "]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "Agentic RAG"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "——不需要提前建索引，Agent 自己去检索、去判断、去拼信息。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "你自己在个人电脑上用，这套做法完全够。但如果要对外提供 AI 问答服务——比如客服机器人、产品帮助中心——很多人同时提问、还要求秒级响应，每次都让 Agent 从头搜一遍文件就太慢了。这时候就需要提前把资料切片、建好索引，用户一提问就能快速匹配到相关内容。这就是前面 RAG 章节讲的做法。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "回头看一下这一节，Agent 搜了网页、打开了链接、抓取了正文、读取了钉钉记录、保存成了文件。但大模型本身不能上网，不能打开文件，更不能读取钉钉。它怎么做到这些事的？"]]], ["h2", {"uuid": "tc71790fltijraw2rmy0", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "2 Agent 的能力从哪来"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "lmo8u6"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "答案是："]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "大模型只负责决定做什么，真正执行的是外部工具。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "你说\"帮我搜三亚攻略\"，大模型判断这个任务需要搜索工具，于是发出一条指令：调用搜索服务，关键词=三亚亲子攻略。搜索引擎返回结果后，大模型再判断哪些链接值得打开，于是又发出指令：调用网页抓取工具，地址=某个链接。大模型并没有上网，它做的是决定调用哪个工具、传什么参数。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "画图也是一样。你说\"帮我画一张日出的图\"，大模型判断需要图像生成工具，发出指令：调用图像生成服务，内容=日出。图片是专门的图像生成服务画的，不是大模型画的。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["img", {"id": "w08vd8", "src": "https://scms-prod-sh-public.oss-cn-shanghai.aliyuncs.com/course_picture/egpehthlfeckxhhfvuia.png", "width": 936, "height": 318}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "搜网页、读文件、画图、查天气，背后都是同一个流程："]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "mtdb0eomeve4", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "你提出需求"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "mtdb0eomeve4", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "大模型判断需要哪个工具，生成一条工具调用指令"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "mtdb0eomeve4", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "千问办公拿着指令去调用对应的外部服务"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "mtdb0eomeve4", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "服务返回结果，大模型再根据结果组织回答"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["img", {"id": "jlbvg7", "src": "https://scms-prod-sh-public.oss-cn-shanghai.aliyuncs.com/course_picture/pxhlylkphrvkwwjfhwbn.svg", "width": 867, "height": 487}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "所以前面你看到的那些操作——联网搜索、打开网页抓取内容、生成文件并保存到文件夹、画图——每一步都是大模型在调用工具。Agent 的能力是两方配合的结果：大模型决定做什么，工具负责真正去做。Agent 能做多少事，取决于它能调用多少工具。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "千问办公预装了一批常用工具（读写文件、执行代码、联网搜索、操作浏览器等），所以前面的任务不需要你额外配置。但有些能力它没有预装——比如查实时路况、规划驾车路线。没有地图工具时，Agent 只能搜网页凑一个模糊答案。怎么给它装上新工具？"]]], ["h2", {"uuid": "8chnc8xa5ymm6aa7tkml", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "3 MCP：给 Agent 接入工具"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "o5alsq"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "接入工具的方式不止一种，MCP（Model Context Protocol）是目前被广泛采用的一种。它的好处是：同一个工具，装到千问办公能用，装到 Claude Code、OpenClaw 这些 AI 助手上也能用，不用重新开发。"]]], ["h3", {"uuid": "z031vsfw36bwdya0c54v"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "3.1 给千问办公装上高德地图"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "假设周末你想带家人去杭州几个景点玩一天，最后到杭州东站坐高铁回家，想让 Agent 帮你规划一条最省时间的驾车路线。在没有地图工具时，Agent 费了很大劲，搜了二十多次网页，最后只能给你一个”大约 20 到 35 分钟”的模糊回答。现在给它装上高德地图，看看有什么不同。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "5whdlvgbey0e", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "打开"]], ["a", {"href": "https://bailian.console.aliyun.com/cn-beijing?tab=app#/mcp-market/detail/amap-maps"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "百炼 Amap Maps 高德地图 MCP 页面"]]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "并登录，点击"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "立即开通"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "。弹窗里的 AMAP_MAPS_API_KEY 不填，直接点击"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "确认开通"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "5whdlvgbey0e", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "开通后点击页面上的 "]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "API Key"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "，复制一个百炼 API Key。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "5whdlvgbey0e", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "回到千问办公，在左侧选择 "]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "扩展 > 连接器"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "（不同版本入口可能不同，也可能在 "]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "设置 >连接器与 MCP"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "），再点击"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "添加 > 粘贴 JSON 配置"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "，粘贴下面这段配置，把 ${DASHSCOPE_API_KEY} 替换成刚复制的 API Key，然后点击"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "导入"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "。"]]], ["code", {"uuid": "28f24r0vkd8d2nbx5k3f", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "{\n \"mcpServers\": {\n \"AliyunBailianMCP_amap-maps\": {\n \"url\": \"https://dashscope.aliyuncs.com/api/v1/mcps/amap-maps/mcp\",\n \"headers\": {\n \"Authorization\": \"Bearer ${DASHSCOPE_API_KEY}\"\n }\n }\n }\n}"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "5whdlvgbey0e", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "配置完成后，回到对话界面，再问同样的问题：“帮我规划一条驾车路线，从西湖出发，去灵隐寺和西溪湿地，最后到杭州东站，时间最短。”"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "Agent 调用高德地图的地理编码和路线规划接口，先查出各地点的坐标，再分别计算不同访问顺序下各段路程的驾车时间，比较后给出一条总用时最短的路线，精确到每段路程的预估时间和距离。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "装上高德地图之后，Agent 就能规划带有具体数据的驾车路线了。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "停下来看一下运行过程：你会看到 Agent 不是只调了一次工具，而是先把地点名称转成坐标、再对不同的访问顺序分别计算驾车时间、最后比较总用时选出最优方案——同一个 MCP 里有多个工具，Agent 会按任务需要自己安排调用顺序和次数。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["img", {"id": "o3ltve", "src": "https://scms-prod-sh-public.oss-cn-shanghai.aliyuncs.com/course_picture/sdkwbncjtnogfycnrxyp.png", "width": 936, "height": 318}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]]], ["h3", {"uuid": "fe45sgvdtf8xalzcvvie"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "3.2 为什么你不用教 Agent 怎么用工具"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "回想一下，你刚才并没有告诉千问办公\"高德地图能做什么、怎么调用、返回什么格式\"。你只是按页面提示粘贴了配置和 Key，剩下的事 Agent 自己就处理好了。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "它怎么知道该怎么用的？因为高德地图 MCP Server 自带了一份"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "工具描述"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "——告诉 AI 自己叫什么、能做什么、需要什么参数。千问办公连上它的那一刻，就自动拿到了这份描述。你没看到，但 Agent 看到了。它大概长这样："]]], ["code", {"uuid": "904ui95vflt7tqoxy6ef", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "工具名称：maps_direction\n功能说明：根据起点和终点规划驾车路线，返回距离、预计时间和途经道路。\n需要参数：\n - origin：起点（如\"西湖\"）\n - destination：终点（如\"杭州东站\"）"]]], ["code", {"uuid": "sytzfmnsmussg25t9zxn", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "工具名称：maps_search_nearby\n功能说明：搜索某个地点附近的餐厅、酒店、加油站等。\n需要参数：\n - location：中心位置（如\"西湖\"）\n - keyword：要搜什么（如\"浙菜餐厅\"）"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "这只是高德地图 MCP 里的两个工具，它实际上还带了地点搜索、实时路况等好几个。每个工具都有名字、功能说明和需要什么参数——Agent 看到这些，就知道什么时候该调哪个、传什么值。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "你什么都不用定义，工具自己会说话——MCP 要求每个工具都带上自己的描述，Agent 连上就能读到。"]]], ["h3", {"uuid": "guqbqn9e91rf7hvnmtgl"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "3.3 去哪里找更多 MCP 工具？"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "下次遇到 Agent 做不了的事——查天气、管日历、连数据库——去 MCP 市场搜一下，大概率有人做好了："]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "n57zo31mp1dy", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["a", {"href": "https://bailian.console.aliyun.com"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "百炼 MCP 广场"]]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "（阿里云百炼平台）——覆盖地图、天气、搜索、文档处理等常见场景，选中后按提示配置即可使用。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["img", {"id": "hegysp", "src": "https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/4EZlweZJYdwEgqxA/img/0ca0bfe0-bb60-48d8-a00a-f5f8e7f94d43#58080", "width": 921, "height": 421}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "xwtd05vzx956", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["a", {"href": "https://modelscope.cn/mcp"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "ModelScope 魔搭社区 MCP 广场"]]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "——社区里开发者自己做的 MCP 工具，覆盖场景更广。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["img", {"id": "lext89", "src": "https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/4EZlweZJYdwEgqxA/img/7349cfa4-3731-46a2-a819-a5bebeccefe7#58094", "width": 924, "height": 296}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]]], ["h2", {"uuid": "hx22qbkgc470hrwyi5nl", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "4 工具不是越多越好"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "t739ga"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "MCP 市场里有上万个工具，接入又方便。是不是应该把能找到的都装上，装得越多 Agent 越强？"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "恰恰相反。"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "工具越多，Agent 反而可能变笨"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "。而且工具本身靠不靠谱、安全不安全，都直接影响使用效果。要理解为什么，得先知道大模型的工作空间是怎么回事。"]]], ["h3", {"uuid": "y2931cwtmzdpagpq7kyz"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "4.1 对话越长，桌面越挤"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "大模型的上下文窗口就像一张办公桌——你的问题、工具清单、之前的对话记录全都堆在上面，总空间有限。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "用实际数字来感受一下。上下文窗口的计量单位叫 "]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "token"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "（一个汉字大约是 1 到 2 个 token）。假设一个模型的上下文窗口是 128000 token（约 12 万字，目前主流模型的水平），然后对话开始：读一份合同 1 万 token、分析一份 Excel 5000 token、几次工具调用的输入输出再几千 token，加上 Agent 每轮的思考和回复，看似很大的 12 万 token 空间，"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "几十轮对话堆下来也会填满"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "数字不用记，记住一点就够："]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "上下文窗口是有限的，每一轮对话都在消耗它"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "。"]]], ["h3", {"uuid": "re6f0dgfca66p2l57uiy"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "4.2 工具描述也在占空间"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "对话过程中桌面会越来越满，这你已经知道了。但还有一件事你可能没意识到："]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "在你开口之前，桌面就已经不是空的了"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "还记得前面讲的工具描述吗？每个工具的“自我介绍”都要放进上下文，Agent 才知道自己能用什么。千问办公预装的几个内置工具，描述加起来还不太占地方。但如果你装了高德地图 MCP、日历 MCP、邮件 MCP、数据库 MCP、新闻 MCP，每个 MCP 都有自己的工具说明，有些 MCP 还提供好几个工具。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "这就涉及到 MCP 的一个特点："]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "每添加一个 MCP Server，它的所有工具描述都要写进上下文"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "。而且很多 MCP Server 不只提供一个工具。比如高德地图 MCP 可能包含“路线规划”“地点搜索”“实时路况”等多个工具，一个 Server 就带来好几条工具描述。你装了 5 个 MCP Server，上下文里可能一下子多出二三十条工具描述。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "可以做一个测试：问 Agent “请把你现在能调用的所有工具列出来，每个工具叫什么、用来做什么、工具描述大概多少字，最后告诉我加起来一共多少字。”你会看到一份比预期长得多的清单——你以为装了几个 MCP，实际是几十个工具，工具描述加起来可能一两万字。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["img", {"id": "x8yxk5", "src": "https://scms-prod-sh-public.oss-cn-shanghai.aliyuncs.com/course_picture/vxkanfeljmbzfxyppsxr.png", "width": 936, "height": 318}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "工具描述越多，留给对话内容的空间就越少。所以用不上的 MCP 先关掉，不相关的话题开新对话窗口，效果往往比硬撑一个长对话要好。"]]], ["h3", {"uuid": "83hln89os54p2o3xm1ks"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "4.3 装 MCP 就是在扩大 Agent 的权限"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "装 MCP 就是给 Agent 开权限。本地 MCP 能读写你电脑上的文件，如果授权范围过大，Agent 可能误改甚至误删你的文件。远程 MCP 会把你的对话内容发到外部服务器，来路不明的 Server 可能截获你的信息——已有公开案例，某个社区邮件 MCP 被发现偷偷转发用户邮件，影响了数百家机构。更隐蔽的风险是，恶意 MCP 可以在工具描述里藏入隐藏指令，引导 Agent 做出你没要求的操作。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "安装或开启 MCP 前，先确认来源是否可信、它要什么权限、是否需要 API Key 或账号授权。日常使用时，记住三条做法："]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "4y33is0coki9", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "只从百炼 MCP 广场、魔搭社区等经过平台审核的渠道安装"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "4y33is0coki9", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "本地 MCP 只开放当前任务需要的文件夹或数据库"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "4y33is0coki9", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "用完之后，用不到的 MCP 先关掉"]]], ["h2", {"uuid": "26v29tsgzfefqi13pvqg", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "动手实验"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "iun8kc"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["h3", {"uuid": "gnhytubxwyt1vc6izit8"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "实验 1：让 Agent 查一个资料文件夹"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "phnjmfkdhqxr", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "准备一个文件夹，放入 5 到 10 份你真实会用的资料，例如会议纪要、旅行攻略、产品说明、项目文档。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "phnjmfkdhqxr", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "混入一份和问题无关的资料，观察 Agent 会不会被带偏。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "phnjmfkdhqxr", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "提出一个需要综合多份资料才能回答的问题，并要求 Agent 在回答中标注每条信息来自哪个文件。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "phnjmfkdhqxr", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "检查它标注的文件是否真实存在、引用是否准确，回答中是否有无法追溯来源的信息。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "phnjmfkdhqxr", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "对现有资料没写明的信息，观察它是否明确说明，而不是直接猜。"]]], ["h3", {"uuid": "6qw2efg65t1gdsac1l3c"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "实验 2：在你关心的场景里跑一次工具协同"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "36rbk877halh", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "选择一个需要外部工具的任务，例如路线规划、天气查询、日历安排或业务资料查询。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "36rbk877halh", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "确认当前 Agent 是否已经接入对应 MCP 或工具。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "36rbk877halh", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "发起一个真实问题，观察运行过程中是否出现工具名、参数和返回结果。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "36rbk877halh", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "对比“未调用工具的文字建议”和“调用工具后的真实结果”有什么差异。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "36rbk877halh", "level": 0, "isOrdered": true, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "decimal", "text": "%1.", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "关闭不相关工具，再运行一次，观察工具列表变短后是否更容易判断。"]]], ["h2", {"uuid": "8hr782zhtsvrtqxj0o4y", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "✅ 本节小结"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "1fduom"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "这节课从\"资料不在手边\"出发，让 Agent 自己去网上找、从平台里取，再到给它装上新工具获取实时数据。背后是同一个逻辑：大模型负责判断做什么，工具负责真正去做。"]]], ["h2", {"uuid": "kz4jl4mmladqgbfeis9u", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "✅ 评价反馈"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "7whfba"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "欢迎你参与"]], ["a", {"href": "https://survey.aliyun.com/apps/zhiliao/ww0sx2B5r"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "阿里云大模型ACA课程调查问卷"]]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "反馈学习体验和课程评价。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "你的批评和鼓励都是我们前进的动力！"]]]]
