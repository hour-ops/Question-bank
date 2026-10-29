# -*- coding: utf-8 -*-
"""Build subjects/c_common/knowledge_base.{json,md} from real DB data."""
import sqlite3, os, sys, io, json, collections, re, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ROOT = r'C:\Users\win11_vmusers\Documents\deepseek-harness\default-workspace\题库项目'
OUT  = os.path.join(ROOT, 'subjects', 'c_common')
os.makedirs(OUT, exist_ok=True)
def ro(p): return sqlite3.connect('file:%s?mode=ro' % p.replace('\\','/'), uri=True)

DBS = ['c_wuhan.sqlite', 'c_hbpu.sqlite']
raw = collections.Counter()           # chapter name -> total questions
raw_by_db = {}                        # db -> Counter
types = collections.Counter()
trust = collections.Counter()
exams = collections.Counter()
empty_rows = {}
for db in DBS:
    con = ro(os.path.join(ROOT, 'data', db)); cur = con.cursor()
    c = collections.Counter()
    cur.execute("SELECT knowledge_point, COUNT(*) FROM questions GROUP BY knowledge_point")
    for kp, n in cur.fetchall():
        c[kp] += n; raw[kp] += n
    raw_by_db[db] = c
    cur.execute("SELECT question_type, COUNT(*) FROM questions GROUP BY question_type")
    for t, n in cur.fetchall(): types[t] += n
    cur.execute("SELECT COALESCE(trust_level,'(null)'), COUNT(*) FROM questions GROUP BY 1")
    for t, n in cur.fetchall(): trust[t] += n
    cur.execute("SELECT COALESCE(exam_title,'(null)'), COUNT(*) FROM questions GROUP BY 1")
    for t, n in cur.fetchall(): exams[t] += n
    empty_rows[db] = sum(n for k, n in c.items() if k is None or not str(k).strip())
    con.close()

TOTAL_Q = sum(raw.values())
NAMED   = sum(n for k, n in raw.items() if k is not None and str(k).strip())
DISTINCT_NAMED = sum(1 for k in raw if k is not None and str(k).strip())

# ---------------- knowledge points ----------------
KP = [
 ('C-01','C语言概述与程序设计基础','C 程序的基本结构（#include/main/函数体）、源程序的编译与运行过程、算法与流程图、常见开发环境。','第1章','C语言概述',[]),
 ('C-02','数据类型、运算符与表达式','int/float/double/char 与取值范围、常量与变量、算术/关系/逻辑/赋值/逗号运算符及优先级结合性、自动与强制类型转换。','第2章','数据类型',[]),
 ('C-03','顺序结构与输入输出','顺序执行、printf 格式控制、scanf 取地址与格式匹配、getchar/putchar、字符数据的输入输出。','第3章','顺序结构',[]),
 ('C-04','选择结构','关系与逻辑表达式、if / if-else / if-else-if、switch-case 与 break 穿透、条件运算符 ?:、嵌套选择。','第4章','选择结构',[]),
 ('C-05','循环结构','while、do-while、for 三段式、break 与 continue、循环嵌套、累加累乘、素数判断与辗转相除等典型循环算法。','第5章','循环结构',[]),
 ('C-06','数组','一维数组的定义引用与初始化、二维数组与矩阵运算、字符数组、数组遍历求最值、冒泡/选择排序、下标越界。','第6章','数组',[]),
 ('C-07','函数与模块化程序设计','函数定义/声明/调用、形参与实参、值传递、数组与指针作参数、递归调用、变量作用域与存储类别（auto/static/extern/register）。','第7章','函数',['C-08']),
 ('C-08','指针','地址与指针变量、指针的初始化与运算、指针与一维/二维数组、指针与字符串、指针作函数参数（传址调用）、返回指针的函数、多级指针。','第8章','指针',['C-06','C-14']),
 ('C-09','结构体、共用体与自定义数据类型','struct 定义与成员访问、结构体数组与结构体指针、union 共用体、enum 枚举、typedef、链表等基础数据结构。','第9章','结构体',['C-06','C-08']),
 ('C-10','文件','文件指针 FILE、fopen/fclose 打开模式、fprintf/fscanf/fgets/fputs/fread/fwrite、文件定位与读写、文本文件与二进制文件。','第10章','文件',[]),
 ('C-11','编译预处理','#define 宏定义（无参与带参、展开与运算符优先级）、#include 文件包含、条件编译 #ifdef/#ifndef/#if。','第11章','编译预处理',[]),
 ('C-12','位运算','按位与 &、按位或 |、按位异或 ^、按位取反 ~、左移 << 与右移 >>、位运算的典型应用。','第12章','位运算',[]),
 ('C-13','常见错误与程序调试','语法错误与逻辑错误的区分、scanf 少取地址、赋值 = 与相等 == 混用、数组下标越界、循环边界与变量未初始化。','第13章','常见错误',['C-02','C-03','C-06']),
 ('C-14','字符串处理','字符串与字符数组的区别、字符串结束符 \\0、strlen/strcpy/strcat/strcmp 等字符串处理函数、sizeof 与 strlen 的区别、字符串与指针。','第14章','字符串',['C-06','C-08']),
 ('C-15','综合项目与案例','整册知识点串联的项目实战：控制台小游戏、综合案例程序。','第15章','综合项目',[]),
]

RULES = [
 ('贪吃蛇','C-15'), ('游戏设计','C-15'), ('综合项目','C-15'), ('综合案例','C-15'), ('项目案例','C-15'),
 ('常见的数据结构','C-09'), ('数据结构基础','C-09'),
 ('常见错误','C-13'), ('越界','C-13'),
 ('流程控制','C-01'),
 ('输入输出','C-03'), ('输入/输出','C-03'), ('键盘输入','C-03'), ('屏幕输出','C-03'), ('scanf','C-03'), ('printf','C-03'),
 ('位运算','C-12'), ('按位与','C-12'), ('按位或','C-12'), ('移位','C-12'),
 ('预处理','C-11'), ('宏定义','C-11'),
 ('文件','C-10'),
 ('字符串','C-14'), ('字符数组','C-14'), ('字符分类','C-14'), ('字符判断','C-14'), ('字符类型','C-14'),
 ('结构体','C-09'), ('共用体','C-09'), ('构造数据类型','C-09'), ('复杂数据类型','C-09'), ('枚举','C-09'), ('链表','C-09'),
 ('指针','C-08'), ('传址','C-08'),
 ('函数','C-07'), ('递归','C-07'), ('存储类别','C-07'), ('局部变量','C-07'), ('作用域','C-07'), ('返回值','C-07'),
 ('数组','C-06'), ('排序','C-06'), ('矩阵','C-06'), ('转置','C-06'), ('元素交换','C-06'), ('冒泡','C-06'), ('对角线','C-06'),
 ('循环','C-05'), ('while','C-05'), ('for ','C-05'), ('do-while','C-05'),
 ('素数','C-05'), ('辗转','C-05'), ('斐波那契','C-05'), ('阶乘','C-05'), ('累加','C-05'), ('累乘','C-05'), ('递推','C-05'),
 ('选择','C-04'), ('分支','C-04'), ('switch','C-04'), ('if','C-04'), ('闰年','C-04'), ('穿透','C-04'),
 ('顺序','C-03'),
 ('数据类型','C-02'), ('运算符','C-02'), ('表达式','C-02'), ('算术运算','C-02'), ('存储与运算','C-02'),
 ('类型转换','C-02'), ('基本知识','C-02'), ('赋值与相等','C-02'),
 ('算法','C-01'), ('概述','C-01'), ('认识C语言','C-01'), ('C语言程序设计基础','C-02'),
 ('程序设计','C-01'), ('C语言','C-01'), ('C 语言','C-01'), ('编程','C-01'), ('为什么要学','C-01'),
]

OVERRIDE = {
 '第3章 流程控制': ('C-01', ['C-03','C-04','C-05']),
 '第3章 顺序和选择结构程序设计': ('C-03', ['C-04']),
 '第8章 结构体等构造数据类型': ('C-09', []),
 '第11章 常见的数据结构': ('C-09', []),
 '第11章 指针和数组': ('C-08', ['C-06']),
 '指针与数组': ('C-08', ['C-06']),
 '二维数组与指针': ('C-08', ['C-06']),
 '指针与一维数组、后置自增运算符': ('C-08', ['C-06','C-02']),
 '指针与字符串': ('C-08', ['C-14']),
 '指针与字符串反转': ('C-08', ['C-14']),
 '指针与字符串复制': ('C-08', ['C-14']),
 '字符串与指针': ('C-14', ['C-08']),
 '函数参数传递（指针传递）': ('C-07', ['C-08']),
 '函数参数传递、指针传递': ('C-07', ['C-08']),
 '指针作为函数参数': ('C-07', ['C-08']),
 '指针作函数参数': ('C-07', ['C-08']),
 '指针作为函数参数，传址调用': ('C-07', ['C-08']),
 '函数返回指针、变量存储类别': ('C-07', ['C-08']),
 '结构体数组': ('C-09', ['C-06']),
 '结构体数组、循环与条件判断': ('C-09', ['C-06','C-05']),
 '结构体数组与指针': ('C-09', ['C-06','C-08']),
 '结构体数组与指针访问成员': ('C-09', ['C-06','C-08']),
 '结构体指针与成员访问': ('C-09', ['C-08']),
 '结构体定义语法': ('C-09', []),
 '枚举类型与 switch 分支': ('C-09', ['C-04']),
 '字符数组与字符串复制': ('C-14', []),
 '字符分类统计': ('C-14', ['C-05']),
 '字符判断与循环': ('C-14', ['C-05']),
 '选择结构、循环结构': ('C-04', ['C-05']),
 '循环结构、算法': ('C-05', ['C-01']),
 '数组、排序算法': ('C-06', ['C-01']),
 '宏定义与运算符优先级': ('C-11', ['C-02']),
 '带参数的宏定义展开及运算符优先级': ('C-11', ['C-02']),
 '逻辑运算符优先级与闰年判断': ('C-02', ['C-04']),
 '第9章 用户自己建立数据类型': ('C-02', ['C-09']),
}

def denum(n): return re.sub(r'^第\s*\d+\s*章\s*', '', n).strip()
def assign(name):
    if name in OVERRIDE: return OVERRIDE[name]
    d = denum(name)
    for kw, kid in RULES:
        if kw in d: return (kid, [])
    return (None, [])

groups = collections.defaultdict(list); secondary_of = {}; unmapped = []
for name in raw:
    if name is None or not str(name).strip(): continue
    kid, sec = assign(str(name))
    if kid is None: unmapped.append(name); continue
    groups[kid].append(name)
    if sec: secondary_of[name] = sec

assert not unmapped, unmapped
assert sum(len(v) for v in groups.values()) == DISTINCT_NAMED

# ---------- sub-points: pulled from real micro-labels + chapter themes ----------
SUB = {
 'C-01': ['C 程序的组成（预处理命令 + 函数）','main 函数与程序入口','算法与流程图','源程序到可执行文件的编译运行过程'],
 'C-02': ['基本数据类型与取值范围','常量与变量的定义与初始化','算术运算符与优先级结合性','关系与逻辑运算符','自增自减与赋值运算符','自动类型转换与强制类型转换'],
 'C-03': ['printf 格式字符','scanf 的地址参数与格式匹配','getchar / putchar','字符数据的输入输出'],
 'C-04': ['if 与 if-else','if-else-if 多分支','switch-case 与 break 穿透','条件运算符 ?:','嵌套选择与悬空 else'],
 'C-05': ['while 与 do-while 的区别','for 的三段式与空语句','break 与 continue 的区别','循环嵌套','累加累乘/素数/辗转相除/斐波那契等典型算法'],
 'C-06': ['一维数组的定义与引用','二维数组与矩阵运算（转置/对角线）','字符数组与字符串','数组遍历求最值','冒泡排序与元素交换','数组下标越界'],
 'C-07': ['函数定义、声明与调用','形参与实参、值传递','数组作函数参数','函数的递归调用','变量作用域与存储类别（static/auto/extern）'],
 'C-08': ['指针变量的定义与初始化','指针与一维数组','指针与二维数组','指针与字符串','指针作函数参数（传址调用）','返回指针的函数','指针与后置自增运算符'],
 'C-09': ['结构体定义语法与成员访问','结构体数组','结构体指针与成员访问','共用体 union','枚举 enum 与 typedef','链表等基础数据结构'],
 'C-10': ['文件指针 FILE','fopen 打开模式与 fclose','fprintf / fscanf','fgets / fputs','fread / fwrite','文件定位与读写'],
 'C-11': ['无参宏定义与展开','带参宏定义与展开','宏定义与运算符优先级','文件包含 #include','条件编译'],
 'C-12': ['按位与 & 、按位或 |','按位异或 ^ 、按位取反 ~','左移与右移','位运算与循环/数组结合的应用'],
 'C-13': ['scanf 少取地址','赋值 = 与相等 == 混用','数组下标越界与循环边界','变量未初始化','关系运算符与赋值运算符的区别'],
 'C-14': ['字符串与字符数组的区别','字符串结束符 \\0','strlen 与 sizeof 的区别','strcpy / strcat / strcmp','字符串复制与数组赋值的限制','字符串与指针'],
 'C-15': ['控制台小游戏','综合案例程序','整册知识点串联项目'],
}

kps = []
for kid, name, desc, num, kw, rel in KP:
    al = sorted(groups.get(kid, []), key=lambda x: (-raw[x], x))
    q  = sum(raw[n] for n in al)
    per_db = {db: sum(raw_by_db[db].get(n, 0) for n in al) for db in DBS}
    flags = {'multi_topic_chapters': {n: secondary_of[n] for n in al if n in secondary_of}}
    item = {
        'id': kid, 'name': name, 'desc': desc,
        'canonical_hint': '教材常见章号：%s（%s）' % (num, kw),
        'alias_chapters': al,
        'alias_count': len(al),
        'question_count': q,
        'question_count_by_db': per_db,
        'sub_points': SUB[kid],
        'related_points': rel,
    }
    if flags['multi_topic_chapters']:
        item['multi_topic_chapters'] = flags['multi_topic_chapters']
        item['multi_topic_question_count'] = sum(raw[n] for n in flags['multi_topic_chapters'])
    kps.append(item)

covered = sum(k['question_count'] for k in kps)
stats = {
 'total_points': len(kps),
 'covered_questions': covered,
 'total_questions': TOTAL_Q,
 'distinct_raw_chapter_names': DISTINCT_NAMED,
 'raw_names_assigned': sum(len(v) for v in groups.values()),
 'raw_names_unmapped': 0,
 'empty_knowledge_point_questions': sum(empty_rows.values()),
 'named_chapter_share_of_all_questions': round(NAMED / TOTAL_Q, 4),
 'note': 'covered_questions 只统计「有章节名的题」；另有 %d 题 knowledge_point 为空串，不在任何知识点内。'
         % sum(empty_rows.values()),
}
doc = {
 'subject': 'c_common',
 'built_at': datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
 'source': {
   'dbs': ['data/%s' % d for d in DBS],
   'questions': TOTAL_Q,
   'raw_chapter_names': DISTINCT_NAMED,
   'raw_chapter_names_incl_empty': DISTINCT_NAMED + 1,
   'questions_with_named_chapter': NAMED,
   'question_type_distribution': dict(types.most_common()),
   'trust_level_distribution': dict(trust.most_common()),
   'exam_title_count': len(exams),
   'exam_titles': dict(exams.most_common()),
   'note': ('c_wuhan 的 knowledge_point 直接取自各校真题/教材章节标注，共 %d 个不同名称（含空串）；'
            'c_hbpu 为湖北理工学院（祁文青 2018 版）体系。两库合计 %d 个不同非空章节名。'
            % (len([k for k in raw_by_db['c_wuhan.sqlite'] if k is not None and str(k).strip()]) + 1, DISTINCT_NAMED)),
 },
 'schema_version': '1.0',
 'merge_rule': '每个原始章节名归属唯一知识点（first-match，规则见 tests/build_c_kb.py）；跨主题的复合章节额外记在 multi_topic_chapters。「第N章」前缀在匹配前被剥离，因为不同教材章号冲突（同样的「第7章」在不同教材里分别指函数、指针或数组）。',
 'knowledge_points': kps,
 'unmapped_chapters': unmapped,
 'unassigned': {
   'reason': 'knowledge_point 为空串，不是章节名，无法映射到任何知识点',
   'rows': {db: empty_rows[db] for db in DBS},
   'total_rows': sum(empty_rows.values()),
   'note': '这些题在 DB 里 knowledge_point 就是空串（c_wuhan 1967 题 / c_hbpu 0 题），不属于「映射失败」，但会拉低原始题的命名覆盖率。',
 },
 'stats': stats,
}
with open(os.path.join(OUT, 'knowledge_base.json'), 'w', encoding='utf-8') as f:
    json.dump(doc, f, ensure_ascii=False, indent=2)

print('unmapped =', len(unmapped))
for k in kps: print('%s %-30s aliases=%-3d q=%-5d multi=%-3d' % (k['id'], k['name'], k['alias_count'], k['question_count'], k.get('multi_topic_question_count', 0)))
print('covered =', covered, '| TOTAL =', TOTAL_Q, '| NAMED =', NAMED, '| empty =', stats['empty_knowledge_point_questions'])
print('distinct named =', DISTINCT_NAMED, '| assigned =', stats['raw_names_assigned'])
print('written', os.path.join(OUT, 'knowledge_base.json'))
