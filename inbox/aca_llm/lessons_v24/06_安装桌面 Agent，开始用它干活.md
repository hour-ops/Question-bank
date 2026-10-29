# 课时6：安装桌面 Agent，开始用它干活

> 来源：edu.aliyun.com/course/3126500/lesson/344730415

## 🚄 前言

你可能已经用 AI 帮自己做过不少事了——写文案、总结材料、分析数据。但每次流程都差不多：把材料贴进对话框，拿到结果，复制出来，自己保存、检查，有问题再贴回去改。一来一回，你一直在 AI 和实际工作之间来回切换。

桌面 Agent 直接运行在你的电脑上，能读写本地文件、调用工具、操作浏览器。你说目标，它自己规划步骤去完成。

这节课装一个桌面 Agent，用它处理真实任务、生成工具、并从手机远程指挥。

## ✏️ 课程目标

学完本课程后，你将能够：

- 让桌面 Agent 从散乱材料中生成报告和可视化页面，并在浏览器里检查修正。

- 用桌面 Agent 生成办公提效、生活辅助等工具。

- 把钉钉或企业微信接到千问办公，躺在沙发上也能继续指挥桌面任务。

## 1 安装千问办公

以千问办公这类桌面 Agent 为例。它的特点是可以访问本地文件，并调用电脑上的工具完成任务。不同产品的界面会变化，但下面的任务方法可以迁移。

打开 千问办公官网，下载你电脑对应系统的安装包，按提示完成安装。首次打开后，按提示注册或登录账号。本课程使用默认设置即可完成实验。具体版本要求、模型档位、计费规则以官网为准。

接下来用它处理几个真实的文件任务。

第一个问题几乎所有人都遇到过：手上有一堆零散材料，需要从中整理出一份完整的报告。文件格式不统一、命名随意、信息分散在各处——以前只能一个个打开，来回翻找，自己拼出结论。

## 2 散乱材料，自动生成报告

周五下午，主管要求下班前提交本周项目周报。

你打开项目文件夹，里面是这周随手攒下来的东西：周一活动筹备会的备忘录、周二改了两版的活动方案、周三导出的报名数据表格、周四去看场地后写的沟通记录、场地方发来的报价单 PDF、还有一张标注了修改意见的海报设计截图和一份待办事项清单。其中一个文件叫"先放这里.md"——你已经忘了里面写的什么。

过去你得把这些一个个点开，先回忆这周做了什么，再从中挑出关键信息，分析数据变化趋势，写成报告，排版检查。光回忆加整理就要一小时。

现在试试让桌面 Agent 来做这件事。

这个任务不只是生成一份文档——我们还要让 Agent 把关键数据做成可视化页面，并自己打开浏览器检查显示效果是否正常。要做到这一点，需要先让 Agent 具备使用浏览器的能力。

打开千问办公桌面客户端，在左侧选择 扩展 → 连接器，找到浏览器连接器，安装并确保它是打开的状态。

安装完成后，在千问办公中输入以下内容，让它帮你下载并解压练习材料：

帮我下载并解压这个文件：https://static-aliyun-doc.oss-cn-hangzhou.aliyuncs.com/education/aca/项目周报与可视化练习材料.zip
解压完成后，继续输入：

把这些材料整理成一份项目周报，包括图片也看一下，要能看出本周完成了什么、在进行中的是什么、有哪些问题需要跟进。再做一个可视化页面展示各任务的进度和关键指标，不要依赖外部库。做完截图看一下，确认图表没有变形、数据没有遗漏。
你会看到 Agent 开始逐个读取文件夹里的内容——文档、表格、PDF、甚至图片。等结果出来后，留意看一下周报里的"需跟进问题"部分：它可能会指出海报设计稿上的日期和活动方案里的日期不一致。你没有让它做这件事——它是同时看了图片和文档之后，自己发现了这个矛盾。

几分钟后，报告和可视化页面都生成了。但生成出来不代表能用——图表可能没显示，数据可能漏了，布局可能错位。所以 Agent 会自己打开浏览器查看页面效果，发现问题就改，改完再看一次。

回头看一下整个过程。你只说了想要什么结果，没有告诉它该怎么做——从哪个文件取什么信息、用什么图表、怎么排版，这些都是它自己规划的。它读取了文件夹里所有格式的文件，包括 PDF 报价单和图片，最终输出的不是一段聊天回复，而是本地可以直接打开的报告文件和可视化网页。你随时可以追加要求让结果更贴合自己的需求——"只看华东区""把客单价加进来""按部门分组再画一版"——Agent 会顺着已有结果继续做，把它调成你真正想要的样子。

## 3 更多 Agent 能帮你做的事

生成报告和可视化页面，只是 Agent 能接的活里的一种。你以前觉得"得会写代码才能做"的事，现在都可以交给它：写一个小工具、调通一个平台的 API、搭一个网站、照着一份文档一步步操作。

### 让它帮你造一个小工具

以前觉得"要是有个小工具能做这件事就好了"，现在可以直接告诉 Agent 你想要什么，它帮你写出来。

比如你最近在背英语单词，想要一个简单的卡片应用——正面显示英文单词和音标，点一下翻转显示中文释义和例句（中英对照）。在千问办公中输入：

帮我做一个英语单词卡片应用。正面显示英文单词和音标，点击翻转显示中文释义、英文例句和例句的中文翻译。先内置 20 个四级高频词，界面要简洁。
如果你有自己整理的单词表，也可以让 Agent 读取你的文件来生成卡片。

不只是卡片应用。任何你想要的小工具，都可以让 Agent 帮你造：

- "帮我做一个番茄钟，25 分钟工作 + 5 分钟休息，能记录今天完成了几轮"

- "做一个'今天吃什么'随机推荐，把我常去的餐厅和口味偏好加进去"

- "帮我做一个视频压缩工具，拖进去就能压缩"

- "做一个工具，把粘贴过来的文字自动整理格式"

做出来的形式也不限：桌面应用、网页小工具、命令行脚本，甚至手机 APP 或小程序，取决于你怎么描述需求。

### 不会写代码，也能调通各种 API

你想用上某个 AI 能力时，常常得自己写代码调它的 API。比如你听说阿里云百炼（阿里云的 AI 模型服务平台）能根据一段文字生成图片，想用它给活动做张海报。你打开百炼的官方文档，发现里面是一段段 API 接口代码，还有一堆参数要填——这些是写给开发者的，不会写代码的人基本无从下手。

现在换一种做法：让千问办公自己去搜百炼的文生图文档，读懂后照着写代码调通。你只要告诉它想要什么：

搜索阿里云百炼的文生图文档，参考文档给活动做一张海报，保存到桌面。
通常它会先搜到文档、读懂，再写代码调用，跑通后把图片存到你电脑上。调通过程要用到百炼 API Key；你还没有的话，也可以让它打开浏览器，去百炼控制台创建一个。 从此以后，很多"只听过、不敢试"的能力，你都能这样够到——门槛从"你会不会写代码"变成了"你能不能把想要什么讲明白"。

### 搭一个简历网站、电商网站、运营平台等

搭网站是另一件听起来门槛很高的事。你在网上搜"怎么搭网站"，出来的流程要装环境、配服务器、写前端页面。照着做一步报一个错，搜报错的文章又各说各的，几天下来连个能打开的页面都没见到。

你可以在千问办公中发送：

搭一个个人网站，用作简历展示，首页放个人介绍、项目经历和联系方式。先做成本地网页。
如果手头暂时没有具体的个人信息，可以先让它用示例数据把页面搭出来，看着整体效果，再慢慢替换成真实内容。

到这里网页还只是一个本地文件：你在浏览器里打开的是自己电脑上的这份，别人打不开。想让别人也能访问、而且二十四小时都能访问，通常要把网页部署到服务器上，再申请域名、配证书，做一串事。现在这些都可以交给千问办公，在对话里说一句：

把这个网页发布成在线链接。
页面确认后它就会发布，你拿到一个任何人都能访问的公网链接，服务器、域名、证书、CDN 都不用你准备。

发布出来的网页默认是静态网页：纯前端展示，适合个人主页、作品集、文档站。但静态网页只负责展示。如果需要实时记录别人的访问、让别人提交表单并把数据保存下来，就要做成动态网页，并在对话里让千问办公挂一个数据库：数据库由它托管，别人填进去的内容直接存进去。电商网站就是典型：顾客下单、留言、问库存，这些内容都要存下来，静态网页做不了。

下面这个自媒体运营平台也一样。选题、脚本、发布、复盘，每个环节的内容都要填进去存下来，所以它也是动态网页。可以这么说：

我要创建一个在线网页，并发布为在线链接，内容是一个自媒体运营平台，覆盖选题、脚本、发布、复盘四个环节。
做完它会以动态网页发布到公网，你在平台里填的内容都存进挂好的数据库。

### 把一篇文档交给它，照着替你操作

你可能会经常遇到这种情况：手头有一篇文档，需要照着一步步操作。

举个例子，你刚入职一家新公司，老板发来一份新人指导文档，里面列着要装哪些软件、在哪些系统里申请权限。这份文档你不用自己一条条对着做。以前照着这种文档，你要一个个下载安装、装失败再搜报错、权限申请到处找入口，一份文档能耗掉大半天。把它发给千问办公，让它按文档替你跑：

按这份新人指导文档下载软件以及申请权限
它能下安装包、能在网页表单里替你填写提交；真到运行安装程序、输管理员密码那一步，它会停下来问你。

再进一步，遇到更复杂的部署也行。比如你在 GitHub 上看到某个开源项目想跑起来，把项目链接发给千问办公，让它装环境、拉代码、把项目跑起来。

从按文档装软件、申请权限，到跑起一个开源项目，只要是照着文档能完成的事，都能交给它试试。

这些场景指向同一件事：电脑上的大部分操作，它都能帮你做。你日常在电脑上反复点的、搜教程搜半天的，大多可以交给它试试。

小贴士：上面看到 Agent 可以操作电脑上的浏览器，而如果想要操作其他的一些可视化软件，通常有两条路。一是开启 Computer Use 功能：让它像人一样看着屏幕、点鼠标、敲键盘去操作软件界面，比如打开钉钉或微信替你发条消息，甚至操作 Photoshop 做抠图；不过这项能力暂时只在 macOS 上支持，操作效率和成功率也有限，后续可以期待它继续扩展。二是让 Agent 去调用软件提供的接口，下一章会讲到。

## 4 不用打字，把想法说给它

你看着刚生成的周报，一次发现好几处要改。用打字提出来，你得逐条想措辞、一边回看页面一边敲，敲完还要回头改一遍；直接说给它就快得多。

千问办公的语音输入不会把你说的话一字一字照抄下来：口头语、重复、说到一半的改口，它都会去掉，输入框里留下的是一段通顺的话。

下面三组是实际录下来的对照：第一段是照着说的话，第二段是输入框里出现的文字。

重复和口头语

嗯，帮我看一下报名数据，就是那个，昨天下午的，呃，昨天下午的那份，看看有没有，怎么说呢，有没有漏掉的，反正就是跟表里对一下。
帮我看一下昨天下午的报名数据，看看有没有漏掉的，跟表里对一下。
说到一半改口

把方案里的时间安排改一下，不对，先别改方案，先把场地确认的邮件发出去，然后再回来改方案。
先别改方案，先把场地确认的邮件发出去，然后再回来改方案
一口气说完不停顿

帮我把这周的进度整理一下发给主管要说清楚场地已经定了但对方要加价两百海报还得改因为日期跟方案对不上报名昨天下午到了一百八十七人需要再核一遍
帮我把这周的进度整理一下发给主管，要说清楚场地已经定了，但对方要加价两百，海报还得改，因为日期跟方案对不上，报名昨天下午到了一百八十七人，还要再核一遍
对照上面三组：重复的说法和口头语没有了，你自己推翻的半句没有留下，一口气说完的地方补上了标点，你要交代的事一件没丢。

要在自己电脑上用起来，先在客户端左侧边栏底部点账户头像，进入 设置 → 语音输入，打开"语音输入"开关，首次使用按系统提示授权麦克风。

开启之后，按一次开始说话（Mac 上默认是右侧 Command 键，Windows 上是右侧 Ctrl 键），输入框旁边的麦克风图标会变色，说明它在听；说完再按一次，说的话就变成文字出现在输入框里。要在 Word、浏览器表单、钉钉这些别的应用里也能说，再打开同一个设置页里的"全局语音输入"开关。

注：开关和按键会随版本变化，以你设置页里的为准。

## 5 离开电脑后继续发指令

上一节你把发指令的方式从打字换成了说话，但任务执行过程中，人不一定一直坐在电脑前。离开座位后，你可能还想追问整理进度、补充要求，或者确认可视化页面检查结果。也可能临时想到一个新任务，想直接从手机发给千问办公。

这时可以把钉钉或企业微信接到千问办公。手机负责发指令和接收回复，真正处理文件、生成可视化页面、使用浏览器检查结果的仍然是电脑上的千问办公。你可以用手机继续已有任务，也可以从手机发起新的桌面任务。

接下来分两步：先配置 IM 频道，让手机和千问办公连上；连好之后，如果想用手机继续电脑上正在运行的任务，还需要把手机会话绑定到那个任务。

通常可以在千问办公左侧找到 IM 频道，进入后找到钉钉或企业微信卡片并点击配置。页面出现二维码后，用手机打开对应应用扫码并确认授权。回到千问办公，看到频道状态变成"已连接"，就说明接好了。

注：钉钉如果出现"准入策略"，个人自测可以选"开放模式"；如果接入团队钉钉，选"配对模式"，等自己允许后再使用。准入策略用于控制谁可以和机器人对话，不是所有 IM 频道都会出现这个选项。

接好后，在钉钉或企业微信里发一句测试消息：

你现在能收到我的消息吗？
如果千问办公在同一个聊天窗口里回复你，就说明手机入口可用。桌面端也会出现这个 IM 会话对应的窗口。

如果要把手机会话绑定到正在运行的桌面任务，可以在手机里发：

/bind
/bind 的作用，是告诉千问办公：这个手机会话接下来要和哪个桌面任务对应。千问办公会列出当前可以绑定的桌面端任务。按列表里的编号再发一条，例如：

/bind 1
绑定后，你在手机里发的消息会转发到这个桌面端任务。你可以追问前面任务的进度：

报告生成完了吗？请告诉我生成了哪些文件，可视化页面检查有没有发现问题。
也可以补充新的要求：

图片压缩工具做好了吗？帮我再加一个功能：压缩前先按文件名排序。
任务结束后，可以在手机里发：

/unbind
/unbind 的作用是解除当前手机会话和桌面任务的绑定。这样手机会话就不再把消息转发给这个桌面任务。需要继续其他任务时，可以重新绑定；如果是新任务，也可以直接在手机里提出新要求。

## 动手实验

前面你已经看到桌面 Agent 如何读取文件、生成报告、自己打开浏览器检查效果。下面的实验让你用同样的方式完成一整套数据分析任务——从拿到原始数据到交付分析报告，全程用自然语言对话，不写一行代码。

实验包含三个场景，你可以选择感兴趣的场景完成：

- 企业财务分析：以财务分析师的视角，基于部门经营数据为 CFO 整理 Q1 经营分析报告

- 学生研究报告：以大三学生的视角，基于实验数据和参考文献撰写完整的学术研究报告

- 教学数据分析：以教务处老师的视角，基于学籍数据完成学业预警分析与管理简报

你将练习：

- 让 AI 读取 Excel、Markdown 等格式的文件并理解其内容结构

- 用自然语言提出分析需求，AI 自动编写代码并执行计算

- 让 AI 生成柱状图、饼图、箱线图等可视化图表

- 分步追问逐步深入，最终生成完整的文字报告

👉点击进入实验：使用千问办公进行数据分析

## ❓ 常见问题

### 我该选哪个模型？

日常用标准档就够了——写文案、整理材料、读文档，甚至本节里"生成周报""造小工具""调百炼 API"这类多步规划任务也能胜任。

标准档跑复杂任务不满意、卡在某一步、改几轮还调不对时，升到高级档再试。

更省的组合用法：高级档做调研、出方案，标准档去执行——前期把方向定准，大批量动作交给标准档。

### 我之前用 QoderWork，怎么迁移到千问办公？

千问办公内置了数据导入功能：进入设置 → 数据导入，选择来源（QoderWork 或其他 Agent 工具），按提示把数据迁移过来即可。

### 还有其他问题怎么办？

相信你还有各种各样的问题——比如"任务完成后能不能弹窗提醒？""企业版能不能支持我和员工一起用？""发布的网页是否支持自定义域名？"这些都能在千问办公的官网文档里查到。

不过在 Agent 时代，你也可以不用自己翻文档：直接在千问办公里把问题问出来，它会自己联网搜索、或者调用其他工具帮你解答。

上一个问题就是例子——即使千问办公没有内置的数据导入功能，你也可以直接在对话框里说一句"帮我把 QoderWork 的数据迁移过来"，剩下的交给它。

## ✅ 本节小结

你描述目标，Agent 自己规划怎么做。需要写代码时它自己写、自己跑；需要检查结果时它自己打开浏览器看。整个过程你可以不断加入自己的个性化要求，把结果调成贴合你真实工作场景的样子——这种深度定制以前要靠程序员排期才能做到，现在你自己就能完成。

下一步可以尝试：把你日常工作里反复做的文件处理交给桌面 Agent，观察哪些环节它能独立完成、哪些需要你补充说明。派活时也可以试一次全程用语音：把一个任务说完发出去，再比对它整理出来的结果和你说话时的顺序差多少、有没有漏掉你最关心的那一条。

## ✅ 评价反馈

欢迎你参与阿里云大模型ACA课程调查问卷反馈学习体验和课程评价。

欢迎你留下具体建议，帮助我们继续改进课程。

eyJ2IjoxLCJqdGkiOiI2M2RjNmQ3OGRmMzY0ZDYxYTE2ZjFmZjMxMDA4MTIwYSIsImxpZCI6MzQ0NzMwNDE1LCJjaWQiOjMxMjY1MDAsInVpZCI6MTQ3MzUzNjI0MjM2MTM2NywiZXhwIjoxNzkxNzM2MTAxfQ.UXT5kFc6sZaRdPEgqiGKR5n83i-Z73lrhY0V-ZUKhEc

["root", {}, ["h2", {"uuid": "yp05mtkf1tgz68qij6fu", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "🚄 前言"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "1dhrro"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "你可能已经用 AI 帮自己做过不少事了——写文案、总结材料、分析数据。但每次流程都差不多：把材料贴进对话框，拿到结果，复制出来，自己保存、检查，有问题再贴回去改。一来一回，你一直在 AI 和实际工作之间来回切换。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "桌面 Agent 直接运行在你的电脑上，能读写本地文件、调用工具、操作浏览器。你说目标，它自己规划步骤去完成。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "这节课装一个桌面 Agent，用它处理真实任务、生成工具、并从手机远程指挥。"]]], ["h2", {"uuid": "zjr0w5v2ujycu7z8o65o", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "✏️ 课程目标"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "qlwo61"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "学完本课程后，你将能够："]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "ced0vu6st87e", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "让桌面 Agent 从散乱材料中生成报告和可视化页面，并在浏览器里检查修正。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "ced0vu6st87e", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "用桌面 Agent 生成办公提效、生活辅助等工具。"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "ced0vu6st87e", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "把钉钉或企业微信接到千问办公，躺在沙发上也能继续指挥桌面任务。"]]], ["h2", {"uuid": "b03x2mwmyjgd458q0ak7", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "1 安装千问办公"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "9g00q8"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "以千问办公这类桌面 Agent 为例。它的特点是可以访问本地文件，并调用电脑上的工具完成任务。不同产品的界面会变化，但下面的任务方法可以迁移。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "打开 "]], ["a", {"href": "https://qwenwork.cn/"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "千问办公官网"]]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "，下载你电脑对应系统的安装包，按提示完成安装。首次打开后，按提示注册或登录账号。本课程使用默认设置即可完成实验。具体版本要求、模型档位、计费规则以官网为准。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "接下来用它处理几个真实的文件任务。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "第一个问题几乎所有人都遇到过：手上有一堆零散材料，需要从中整理出一份完整的报告。文件格式不统一、命名随意、信息分散在各处——以前只能一个个打开，来回翻找，自己拼出结论。"]]], ["h2", {"uuid": "quyxqtpf8cz3l1q0bpjg", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "2 散乱材料，自动生成报告"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "awy8e3"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "周五下午，主管要求下班前提交本周项目周报。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "你打开项目文件夹，里面是这周随手攒下来的东西：周一活动筹备会的备忘录、周二改了两版的活动方案、周三导出的报名数据表格、周四去看场地后写的沟通记录、场地方发来的报价单 PDF、还有一张标注了修改意见的海报设计截图和一份待办事项清单。其中一个文件叫\"先放这里.md\"——你已经忘了里面写的什么。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "过去你得把这些一个个点开，先回忆这周做了什么，再从中挑出关键信息，分析数据变化趋势，写成报告，排版检查。光回忆加整理就要一小时。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "现在试试让桌面 Agent 来做这件事。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "这个任务不只是生成一份文档——我们还要让 Agent 把关键数据做成可视化页面，并自己打开浏览器检查显示效果是否正常。要做到这一点，需要先让 Agent 具备使用浏览器的能力。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "打开千问办公桌面客户端，在左侧选择 扩展 → 连接器，找到浏览器连接器，安装并确保它是打开的状态。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "安装完成后，在千问办公中输入以下内容，让它帮你下载并解压练习材料："]]], ["code", {"uuid": "s5h95v6naqu8yngvdq5n", "language": "text-x-markdown"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "帮我下载并解压这个文件：https://static-aliyun-doc.oss-cn-hangzhou.aliyuncs.com/education/aca/项目周报与可视化练习材料.zip"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "解压完成后，继续输入："]]], ["code", {"uuid": "m2kdnkf2mxxkv9fv2syi", "language": "text-x-markdown"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "把这些材料整理成一份项目周报，包括图片也看一下，要能看出本周完成了什么、在进行中的是什么、有哪些问题需要跟进。再做一个可视化页面展示各任务的进度和关键指标，不要依赖外部库。做完截图看一下，确认图表没有变形、数据没有遗漏。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "你会看到 Agent 开始逐个读取文件夹里的内容——文档、表格、PDF、甚至图片。等结果出来后，留意看一下周报里的\"需跟进问题\"部分：它可能会指出海报设计稿上的日期和活动方案里的日期不一致。你没有让它做这件事——它是同时看了图片和文档之后，自己发现了这个矛盾。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "几分钟后，报告和可视化页面都生成了。但生成出来不代表能用——图表可能没显示，数据可能漏了，布局可能错位。所以 Agent 会自己打开浏览器查看页面效果，发现问题就改，改完再看一次。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["img", {"id": "51of14", "src": "https://img.alicdn.com/imgextra/i4/O1CN01lNgDuDXAyEE4Mtkp_!!6000000001450-2-tps-2152-731.png", "width": 936, "height": 318}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "回头看一下整个过程。你只说了想要什么结果，没有告诉它该怎么做——从哪个文件取什么信息、用什么图表、怎么排版，这些都是它自己规划的。它读取了文件夹里所有格式的文件，包括 PDF 报价单和图片，最终输出的不是一段聊天回复，而是本地可以直接打开的报告文件和可视化网页。你随时可以追加要求让结果更贴合自己的需求——\"只看华东区\"\"把客单价加进来\"\"按部门分组再画一版\"——Agent 会顺着已有结果继续做，把它调成你真正想要的样子。"]]], ["h2", {"uuid": "d61gqphg03fccdfrk4ol", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "3 更多 Agent 能帮你做的事"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "orh6jr"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "生成报告和可视化页面，只是 Agent 能接的活里的一种。你以前觉得\"得会写代码才能做\"的事，现在都可以交给它：写一个小工具、调通一个平台的 API、搭一个网站、照着一份文档一步步操作。"]]], ["h3", {"uuid": "12qof1o704erupiue6p1"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "让它帮你造一个小工具"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "以前觉得\"要是有个小工具能做这件事就好了\"，现在可以直接告诉 Agent 你想要什么，它帮你写出来。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "比如你最近在背英语单词，想要一个简单的卡片应用——正面显示英文单词和音标，点一下翻转显示中文释义和例句（中英对照）。在千问办公中输入："]]], ["code", {"uuid": "pe8fr1edmdjqcr7w223i", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "帮我做一个英语单词卡片应用。正面显示英文单词和音标，点击翻转显示中文释义、英文例句和例句的中文翻译。先内置 20 个四级高频词，界面要简洁。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "如果你有自己整理的单词表，也可以让 Agent 读取你的文件来生成卡片。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["img", {"id": "vo46pu", "src": "https://img.alicdn.com/imgextra/i1/O1CN017lCcZg1dwualbE3Ze_!!6000000003801-2-tps-1792-608.png", "width": 936, "height": 318}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "不只是卡片应用。任何你想要的小工具，都可以让 Agent 帮你造："]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "7qx6347v78hg", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "\"帮我做一个番茄钟，25 分钟工作 + 5 分钟休息，能记录今天完成了几轮\""]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "7qx6347v78hg", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "\"做一个'今天吃什么'随机推荐，把我常去的餐厅和口味偏好加进去\""]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "7qx6347v78hg", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "\"帮我做一个视频压缩工具，拖进去就能压缩\""]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "7qx6347v78hg", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "\"做一个工具，把粘贴过来的文字自动整理格式\""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "做出来的形式也不限：桌面应用、网页小工具、命令行脚本，甚至手机 APP 或小程序，取决于你怎么描述需求。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["img", {"id": "npxh3q", "src": "https://img.alicdn.com/imgextra/i2/O1CN011ZMGwH29OcdzE9xFD_!!6000000008058-2-tps-1792-608.png", "width": 936, "height": 318}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]]], ["h3", {"uuid": "wjlmmc2m4kzi187jrjmm"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "不会写代码，也能调通各种 API"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "你想用上某个 AI 能力时，常常得自己写代码调它的 API。比如你听说阿里云百炼（阿里云的 AI 模型服务平台）能根据一段文字生成图片，想用它给活动做张海报。你打开百炼的官方文档，发现里面是一段段 API 接口代码，还有一堆参数要填——这些是写给开发者的，不会写代码的人基本无从下手。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "现在换一种做法：让千问办公自己去搜百炼的文生图文档，读懂后照着写代码调通。你只要告诉它想要什么："]]], ["code", {"uuid": "labnsshj0h31a93j0bls", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "搜索阿里云百炼的文生图文档，参考文档给活动做一张海报，保存到桌面。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "通常它会先搜到文档、读懂，再写代码调用，跑通后把图片存到你电脑上。调通过程要用到百炼 API Key；你还没有的话，也可以让它打开浏览器，去百炼控制台创建一个。 从此以后，很多\"只听过、不敢试\"的能力，你都能这样够到——门槛从\"你会不会写代码\"变成了\"你能不能把想要什么讲明白\"。"]]], ["h3", {"uuid": "1d1qj04xl1i56095asmu"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "搭一个简历网站、电商网站、运营平台等"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "搭网站是另一件听起来门槛很高的事。你在网上搜\"怎么搭网站\"，出来的流程要装环境、配服务器、写前端页面。照着做一步报一个错，搜报错的文章又各说各的，几天下来连个能打开的页面都没见到。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "你可以在千问办公中发送："]]], ["code", {"uuid": "4aig09836tqwywrf2ltz", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "搭一个个人网站，用作简历展示，首页放个人介绍、项目经历和联系方式。先做成本地网页。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "如果手头暂时没有具体的个人信息，可以先让它用示例数据把页面搭出来，看着整体效果，再慢慢替换成真实内容。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "到这里网页还只是一个本地文件：你在浏览器里打开的是自己电脑上的这份，别人打不开。想让别人也能访问、而且二十四小时都能访问，通常要把网页部署到服务器上，再申请域名、配证书，做一串事。现在这些都可以交给千问办公，在对话里说一句："]]], ["code", {"uuid": "wdbblzks3ehkuqh02qo7", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "把这个网页发布成在线链接。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "页面确认后它就会发布，你拿到一个任何人都能访问的公网链接，服务器、域名、证书、CDN 都不用你准备。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "发布出来的网页默认是静态网页：纯前端展示，适合个人主页、作品集、文档站。但静态网页只负责展示。如果需要实时记录别人的访问、让别人提交表单并把数据保存下来，就要做成动态网页，并在对话里让千问办公挂一个数据库：数据库由它托管，别人填进去的内容直接存进去。电商网站就是典型：顾客下单、留言、问库存，这些内容都要存下来，静态网页做不了。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "下面这个自媒体运营平台也一样。选题、脚本、发布、复盘，每个环节的内容都要填进去存下来，所以它也是动态网页。可以这么说："]]], ["code", {"uuid": "rxifhxu6ehqyy7qqc9uw", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "我要创建一个在线网页，并发布为在线链接，内容是一个自媒体运营平台，覆盖选题、脚本、发布、复盘四个环节。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "做完它会以动态网页发布到公网，你在平台里填的内容都存进挂好的数据库。"]]], ["h3", {"uuid": "0u9rqwpxtosw3mv55vpb"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "把一篇文档交给它，照着替你操作"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "你可能会经常遇到这种情况：手头有一篇文档，需要照着一步步操作。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "举个例子，你刚入职一家新公司，老板发来一份新人指导文档，里面列着要装哪些软件、在哪些系统里申请权限。这份文档你不用自己一条条对着做。以前照着这种文档，你要一个个下载安装、装失败再搜报错、权限申请到处找入口，一份文档能耗掉大半天。把它发给千问办公，让它按文档替你跑："]]], ["code", {"uuid": "9rvo2g20vb3wpd5o69xs", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "按这份新人指导文档下载软件以及申请权限"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "它能下安装包、能在网页表单里替你填写提交；真到运行安装程序、输管理员密码那一步，它会停下来问你。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "再进一步，遇到更复杂的部署也行。比如你在 GitHub 上看到某个开源项目想跑起来，把项目链接发给千问办公，让它装环境、拉代码、把项目跑起来。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "从按文档装软件、申请权限，到跑起一个开源项目，只要是照着文档能完成的事，都能交给它试试。"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "lkv52a"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "这些场景指向同一件事：电脑上的大部分操作，它都能帮你做。你日常在电脑上反复点的、搜教程搜半天的，大多可以交给它试试。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["img", {"id": "xyyojh", "src": "https://img.alicdn.com/imgextra/i4/O1CN01LUFzpt1LtYc4KYIUp_!!6000000001357-2-tps-1792-608.png", "width": 900, "height": 305}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}, "blockquote": true}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "小贴士：上面看到 Agent 可以操作电脑上的浏览器，而如果想要操作其他的一些可视化软件，通常有两条路。一是开启 "]], ["a", {"href": "https://help.aliyun.com/zh/qwenwork/computer-use"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "Computer Use"]]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, " 功能：让它像人一样看着屏幕、点鼠标、敲键盘去操作软件界面，比如打开钉钉或微信替你发条消息，甚至操作 Photoshop 做抠图；不过这项能力暂时只在 macOS 上支持，操作效率和成功率也有限，后续可以期待它继续扩展。二是让 Agent 去调用软件提供的接口，下一章会讲到。"]]], ["h2", {"uuid": "yjrw4gtz3nxpv2bnanpe", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "4 不用打字，把想法说给它"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "xvqgj4"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "你看着刚生成的周报，一次发现好几处要改。用打字提出来，你得逐条想措辞、一边回看页面一边敲，敲完还要回头改一遍；直接说给它就快得多。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "千问办公的语音输入不会把你说的话一字一字照抄下来：口头语、重复、说到一半的改口，它都会去掉，输入框里留下的是一段通顺的话。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "下面三组是实际录下来的对照：第一段是照着说的话，第二段是输入框里出现的文字。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "重复和口头语"]]], ["code", {"uuid": "hv4ygxsirbvs0g4o4puw", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "嗯，帮我看一下报名数据，就是那个，昨天下午的，呃，昨天下午的那份，看看有没有，怎么说呢，有没有漏掉的，反正就是跟表里对一下。"]]], ["code", {"uuid": "ceiylu7qyburwh8o4f5d", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "帮我看一下昨天下午的报名数据，看看有没有漏掉的，跟表里对一下。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "说到一半改口"]]], ["code", {"uuid": "mz76tj21swlhki9q1noy", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "把方案里的时间安排改一下，不对，先别改方案，先把场地确认的邮件发出去，然后再回来改方案。"]]], ["code", {"uuid": "fs5kh5p4lwmo3j6bypgb", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "先别改方案，先把场地确认的邮件发出去，然后再回来改方案"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "一口气说完不停顿"]]], ["code", {"uuid": "ojnnxqnfx7w6qouxruhr", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "帮我把这周的进度整理一下发给主管要说清楚场地已经定了但对方要加价两百海报还得改因为日期跟方案对不上报名昨天下午到了一百八十七人需要再核一遍"]]], ["code", {"uuid": "eu8w2yjbf0j9sbdu46d2", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "帮我把这周的进度整理一下发给主管，要说清楚场地已经定了，但对方要加价两百，海报还得改，因为日期跟方案对不上，报名昨天下午到了一百八十七人，还要再核一遍"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "对照上面三组：重复的说法和口头语没有了，你自己推翻的半句没有留下，一口气说完的地方补上了标点，你要交代的事一件没丢。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "要在自己电脑上用起来，先在客户端左侧边栏底部点账户头像，进入 "]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "设置 → 语音输入"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "，打开\"语音输入\"开关，首次使用按系统提示授权麦克风。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "开启之后，按一次开始说话（Mac 上默认是右侧 Command 键，Windows 上是右侧 Ctrl 键），输入框旁边的麦克风图标会变色，说明它在听；说完再按一次，说的话就变成文字出现在输入框里。要在 Word、浏览器表单、钉钉这些别的应用里也能说，再打开同一个设置页里的\"全局语音输入\"开关。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}, "blockquote": true}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "注：开关和按键会随版本变化，以你设置页里的为准。"]]], ["h2", {"uuid": "1y0frrg067f08lxn1x84", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "5 离开电脑后继续发指令"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "wfpjw4"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "上一节你把发指令的方式从打字换成了说话，但任务执行过程中，人不一定一直坐在电脑前。离开座位后，你可能还想追问整理进度、补充要求，或者确认可视化页面检查结果。也可能临时想到一个新任务，想直接从手机发给千问办公。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "这时可以把钉钉或企业微信接到千问办公。手机负责发指令和接收回复，真正处理文件、生成可视化页面、使用浏览器检查结果的仍然是电脑上的千问办公。你可以用手机继续已有任务，也可以从手机发起新的桌面任务。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "接下来分两步：先配置 IM 频道，让手机和千问办公连上；连好之后，如果想用手机继续电脑上正在运行的任务，还需要把手机会话绑定到那个任务。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "通常可以在千问办公左侧找到 "]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "IM 频道"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "，进入后找到钉钉或企业微信卡片并点击配置。页面出现二维码后，用手机打开对应应用扫码并确认授权。回到千问办公，看到频道状态变成\"已连接\"，就说明接好了。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}, "blockquote": true}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "注：钉钉如果出现\"准入策略\"，个人自测可以选\"开放模式\"；如果接入团队钉钉，选\"配对模式\"，等自己允许后再使用。准入策略用于控制谁可以和机器人对话，不是所有 IM 频道都会出现这个选项。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "接好后，在钉钉或企业微信里发一句测试消息："]]], ["code", {"uuid": "k0dnyzaqk8kgnin5i4i9", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "你现在能收到我的消息吗？"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "如果千问办公在同一个聊天窗口里回复你，就说明手机入口可用。桌面端也会出现这个 IM 会话对应的窗口。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "如果要把手机会话绑定到正在运行的桌面任务，可以在手机里发："]]], ["code", {"uuid": "ldv4zyozwk5vv53fn750", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "/bind"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "/bind 的作用，是告诉千问办公：这个手机会话接下来要和哪个桌面任务对应。千问办公会列出当前可以绑定的桌面端任务。按列表里的编号再发一条，例如："]]], ["code", {"uuid": "yaczmcmgmu1z3gxs2jei", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "/bind 1"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "绑定后，你在手机里发的消息会转发到这个桌面端任务。你可以追问前面任务的进度："]]], ["code", {"uuid": "emg2dvvfnjuc4poqt9eq", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "报告生成完了吗？请告诉我生成了哪些文件，可视化页面检查有没有发现问题。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "也可以补充新的要求："]]], ["code", {"uuid": "em4ysbe6w0wrrs8azrjy", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "图片压缩工具做好了吗？帮我再加一个功能：压缩前先按文件名排序。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "任务结束后，可以在手机里发："]]], ["code", {"uuid": "lxn269teudo5xsvvrmk0", "language": "plaintext"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "/unbind"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "/unbind 的作用是解除当前手机会话和桌面任务的绑定。这样手机会话就不再把消息转发给这个桌面任务。需要继续其他任务时，可以重新绑定；如果是新任务，也可以直接在手机里提出新要求。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["img", {"id": "08swh9", "src": "https://scms-prod-sh-public.oss-cn-shanghai.aliyuncs.com/course_picture/jwqcipulixnrunkgwgsg.png", "width": 936, "height": 318}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]]], ["h2", {"uuid": "pp6ld0grigyqq1hs5ckv", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "动手实验"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "sudfmv"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "前面你已经看到桌面 Agent 如何读取文件、生成报告、自己打开浏览器检查效果。下面的实验让你用同样的方式完成一整套数据分析任务——从拿到原始数据到交付分析报告，全程用自然语言对话，不写一行代码。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "实验包含三个场景，你可以选择感兴趣的场景完成："]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "ztkgqkkbcyw3", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "企业财务分析："]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "以财务分析师的视角，基于部门经营数据为 CFO 整理 Q1 经营分析报告"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "ztkgqkkbcyw3", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "学生研究报告："]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "以大三学生的视角，基于实验数据和参考文献撰写完整的学术研究报告"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "ztkgqkkbcyw3", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "教学数据分析："]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "以教务处老师的视角，基于学籍数据完成学业预警分析与管理简报"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "你将练习："]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "0svobn7u1g8e", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "让 AI 读取 Excel、Markdown 等格式的文件并理解其内容结构"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "0svobn7u1g8e", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "用自然语言提出分析需求，AI 自动编写代码并执行计算"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "0svobn7u1g8e", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "让 AI 生成柱状图、饼图、箱线图等可视化图表"]]], ["p", {"spacing": {"line": 1.15, "lineRule": "auto"}, "list": {"listId": "0svobn7u1g8e", "level": 0, "isOrdered": false, "isTaskList": false, "listStyleType": "SARR_SDIO_SCIR", "symbolStyle": {}, "listStyle": {"format": "bullet", "text": "➔", "align": "left"}, "hideSymbol": false}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "分步追问逐步深入，最终生成完整的文字报告"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "👉"]], ["a", {"href": "https://developer.aliyun.com/adc/scenario/exp/c6cce4802824473f8c32450b80e9034c"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "点击进入实验：使用千问办公进行数据分析"]]]], ["h2", {"uuid": "zc0dsideooudpnc9ayl1", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "❓ 常见问题"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "aecsrp"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["h3", {"uuid": "23azw4x5kggvh8ous8lq"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "我该选哪个模型？"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "日常用标准档就够了"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "——写文案、整理材料、读文档，甚至本节里\"生成周报\"\"造小工具\"\"调百炼 API\"这类多步规划任务也能胜任。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "标准档跑复杂任务不满意、卡在某一步、改几轮还调不对时，升到高级档再试。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "更省的组合用法："]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "高级档做调研、出方案，标准档去执行"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "——前期把方向定准，大批量动作交给标准档。"]]], ["h3", {"uuid": "x9n8dy4tw7glgwhf6ukg"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "我之前用 QoderWork，怎么迁移到千问办公？"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "千问办公内置了数据导入功能：进入"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "设置 → 数据导入"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "，选择来源（QoderWork 或其他 Agent 工具），按提示把数据迁移过来即可。"]]], ["h3", {"uuid": "tes0gwoqmfytqsy3q33e"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "还有其他问题怎么办？"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "相信你还有各种各样的问题——比如\"任务完成后能不能弹窗提醒？\"\"企业版能不能支持我和员工一起用？\"\"发布的网页是否支持自定义域名？\"这些都能在千问办公的官网文档里查到。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "不过在 Agent 时代，你也可以不用自己翻文档："]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true}, "直接在千问办公里把问题问出来"]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "，它会自己联网搜索、或者调用其他工具帮你解答。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "上一个问题就是例子——即使千问办公没有内置的数据导入功能，你也可以直接在对话框里说一句\"帮我把 QoderWork 的数据迁移过来\"，剩下的交给它。"]]], ["h2", {"uuid": "i54jpbs77986au62f5s4", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "✅ 本节小结"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "9me2kd"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "你描述目标，Agent 自己规划怎么做。需要写代码时它自己写、自己跑；需要检查结果时它自己打开浏览器看。整个过程你可以不断加入自己的个性化要求，把结果调成贴合你真实工作场景的样子——这种深度定制以前要靠程序员排期才能做到，现在你自己就能完成。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "下一步可以尝试：把你日常工作里反复做的文件处理交给桌面 Agent，观察哪些环节它能独立完成、哪些需要你补充说明。派活时也可以试一次全程用语音：把一个任务说完发出去，再比对它整理出来的结果和你说话时的顺序差多少、有没有漏掉你最关心的那一条。"]]], ["h2", {"uuid": "r56tf9yjbzmq0ykfmngw", "spacing": {"before": 21.333333333333332, "after": 12, "line": 0.8529411764705882}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf", "bold": true, "sz": 16, "szUnit": "pt"}, "✅ 评价反馈"]]], ["hr", {"color": "#D8D8D8", "width": "100%", "sz": 1, "id": "sdffh6"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, ""]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "欢迎你参与"]], ["a", {"href": "https://survey.aliyun.com/apps/zhiliao/ww0sx2B5r"}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "阿里云大模型ACA课程调查问卷"]]], ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "反馈学习体验和课程评价。"]]], ["p", {"ind": {"left": 0}, "spacing": {"line": 1}}, ["span", {"data-type": "text"}, ["span", {"data-type": "leaf"}, "欢迎你留下具体建议，帮助我们继续改进课程。"]]]]
