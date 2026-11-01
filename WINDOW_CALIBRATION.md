# 时间窗口导出：校准实验结果

> 实验日期 2026-11-01，只读运行，未修改任何源码，未写入微信目录。
> 数据源：本机微信数据目录（当前账号 `wxid_***`，2 个消息分片）。
> 目标：为方案 B（`--since/--until/--last-days`）落地前消除不确定项。

---

## 一、结论速览

| 待验证假设 | 结果 | 影响 |
|---|---|---|
| `sort_seq` 有索引，窗口过滤能走索引 | ✅ 命中 `INDEX ..._SORTSEQ` | 方案 B 的 SQL 改造成本极低 |
| `create_time` 也能作为过滤条件 | ❌ 走 `SCAN` 全表 | **禁止用 create_time 做窗口条件** |
| SQL 窗口结果 == 全量导出后过滤 | ✅ 3/3 会话完全一致 | 正确性可用对账保证 |
| 分片按时间严格切分 | ✅ 两分片时间区间不相交 | 跨分片窗口天然正确 |
| 分片可提前剪枝（跳过旧分片） | ❌ `.material` 加密，mtime 不可靠 | **放弃剪枝，方案 B 简化** |
| WAL 中的最新消息可读 | ✅ 读到 11:24:38（实时） | `until` 语义需特别处理 |
| `create_time` 存在秒/毫秒混用 | ❌ 抽查 30 张表全为 10 位 | 换算口径可统一，但兜底仍保留 |

**总体判断：方案 B 可行，且比原计划更简单——去掉分片剪枝后只剩「一个函数加 WHERE + 一条参数链」。**

---

## 二、实验明细

### 1. 索引与查询计划

```sql
-- ✅ 走索引
SELECT * FROM Msg_78e3a19... WHERE sort_seq >= ? AND sort_seq < ?
  -> SEARCH Msg_78e3a19... USING INDEX Msg_78e3a19..._SORTSEQ (sort_seq>? AND sort_seq<?)

-- ❌ 全表扫描
SELECT * FROM Msg_78e3a19... WHERE create_time >= ? AND create_time < ?
  -> SCAN Msg_78e3a19...

-- 无 WHERE 时用覆盖索引（仅计数场景）
SELECT COUNT(*) FROM Msg_78e3a19...
  -> SCAN ... USING COVERING INDEX ..._SORTSEQ
```

每个 `Msg_*` 表有 4 个索引：

| 索引 | 列 | 用途 |
|---|---|---|
| `*_SORTSEQ` | `sort_seq` | **窗口过滤** |
| `*_TYPE_SEQ` | `local_type, sort_seq` | 按类型筛选（媒体阶段） |
| `*_SERVERID` | `server_id` | 去重/同步 |
| `*_SENDERID` | `real_sender_id` | 按发送者筛选 |

`create_time` **无索引**。用它做窗口条件会让「加速」变成「先全扫再过滤」，比不加 WHERE 更慢。

### 2. sort_seq 的真实语义

```
sort_seq = create_time * 1000 + 同秒内序号(0..7)
create_time = 秒级 Unix 时间戳（全 10 位）
```

抽样（`会话A`）：

| create_time | sort_seq | 差值 |
|---|---|---|
| 1757824743 | 1757824743000 | 0 |
| 1757824743 | 1757824743001 | 1 |
| 1757824743 | 1757824743002 | 2 |
| 1757824762 | 1757824762000 | 0 |

同秒内多条的实测上限：

```
同秒 Top5（create_time, 条数）: (1767199265, 8), (1767198296, 6), (1767199311, 5), ...
同秒最大条数: 8
```

**关键含义：`sort_seq` 的毫秒位不是时间精度，是同秒排序序号。**
所以：
- 窗口边界只能精确到**秒**，`10:35:32.500` 这种亚秒参数无意义
- 反过来，同一秒内的 8 条消息可以靠序号精确切分，秒级边界不会「一刀切掉半秒」
- 换算规则：`since_ms = int(timestamp) * 1000`，`until_ms = int(timestamp) * 1000`，区间用 `[since, until)`

`create_time` 位数分布（抽查 30 张 `Msg_*` 表，取 MIN/MAX 共 60 个样本）：**全部 10 位**，未发现毫秒混用。

### 3. 对账结果

SQL 窗口取数 vs 已导出全量 JSON 按 `time` 过滤，比较 `local_id` 集合：

| 会话 | 窗口 | SQL | JSON | 一致 |
|---|---|---:|---:|---|
| 会话A | 2026-03-01 ~ 2026-04-15 | 323 | 323 | ✅ |
| 会话B | 2026-02-01 ~ 2026-03-01 | 0 | 0 | ✅ 空窗口不崩 |
| 会话C | 2026-01-01 ~ 2026-06-01 | 208 | 208 | ✅ |

空窗口返回 0 行，会走 `EmptyConversationError` → 批量索引记 `skipped_empty`，**无需额外改批量逻辑**。

### 4. 分片时间边界

| 分片 | 时间范围 | 行数（会话A） | 体积 |
|---|---|---|---:|
| `message_0.db` | 2025-09-14 12:39 → 2026-06-17 07:36 | 4,044 | 687.5 MB |
| `message_1.db` | 2026-06-17 21:55 → 2026-11-01 11:24 | 666 | 351.5 MB |

结论：**不相交**，跨分片窗口天然正确，不需要在做窗口过滤时关心消息落在哪个库。

### 5. WAL 状态

| 文件 | 大小 | mtime |
|---|---:|---|
| `message_0.db-wal` | 4.00 MB | 10-21 21:42（静止） |
| `message_1.db-wal` | 4.00 MB | **11-01 11:24（活跃）** |

实测 `message_1.db` 内最大 `sort_seq` → `2026-11-01 11:24:38`，与系统时间同步，证明 WAL 增量被上游正确合并。

### 6. 性能

**固定成本（与窗口无关）：**

| 操作 | 耗时 |
|---|---:|
| 首次打开 `message_0.db` | 6,359 ms |
| 首次打开 `message_1.db` | 3,245 ms |
| 再次打开 `message_0.db`（WAL 静止，命中缓存） | 1 ms |
| 再次打开 `message_1.db`（WAL 活跃，触发重建） | 3,447 ms |

**SQL 层（窗口 vs 全量）：**

| 会话 | 分片 | 行数 | 全量 | 7天窗口 | 占比 |
|---|---|---:|---:|---:|---:|
| 会话D | msg_0 | 249,936 | 207.0 ms | **2.0 ms** | 2.02% |
| 会话D | msg_1 | 152,841 | 118.0 ms | **8.6 ms** | 9.87% |
| 会话E | msg_0 | 18,786 | 10.5 ms | 0.6 ms | 6.84% |
| 会话E | msg_1 | 27,517 | 14.3 ms | 2.9 ms | 9.60% |

SQL 层提速 40–100×，但绝对值是毫秒级。**真正的收益在下游**：解析、媒体解密、JSON 序列化、写盘。以 `会话D` 为参照（392,960 条 → 60 s / 268 MB），近 7 天约 2 万条（5%），预计降到 **3–6 s / ~15 MB**。

### 7. 分片剪枝失败的原因

原始设想：只扫最新分片，跳过 687 MB 的 `message_0.db`（省 6.4 s）。

两条路都堵死：

1. **`.material` 文件加密** —— `message_1.db-first.material` / `-last.material` 头部是 SQLCipher salt（`36 22 0b 2d ...`），无法在解密前读到分片时间范围。
2. **mtime 不可靠** —— `message_0.db` 的 mtime 是 10-21，但内容截止 6-17，说明微信会重写库文件头/页而不改时间边界。

而且只有 2 个分片，省 6.4 s 换一堆启发式判断，不划算。

---

## 三、对原方案的三处修正

| # | 原计划 | 修正后 |
|---|---|---|
| 1 | `sort_seq` 为主、`create_time` 双条件兜底 | **只用 `sort_seq`**。`create_time` 无索引，作为 OR 条件会让整个查询退化为全表扫。仅当某行 `sort_seq` 为空时才在 Python 侧补充判断（实测为 0 行） |
| 2 | 第二阶段加分片剪枝 | **取消**。`.material` 加密 + mtime 不可信，无低成本剪枝路径 |
| 3 | 窗口精确到毫秒 | **精确到秒**。`sort_seq` 的毫秒位是同秒序号，不是时间 |

---

## 四、实现清单（精确到行号）

| 位置 | 改动 |
|---|---|
| `exporter_core.py:743` | `load_rows(db, username)` → `load_rows(db, username, since=None, until=None)`；SQL 加 `WHERE sort_seq >= ? AND sort_seq < ?`（动态拼接，两参数独立可选）；`ORDER BY sort_seq` 走索引 |
| `exporter_core.py:2570` | `rows = load_rows(db, username)` → 透传 `since/until` |
| `exporter_core.py:2527` | `_export_chat_impl(...)` 签名加 `since=None, until=None` |
| `exporter_core.py:3257` | 批量循环调 `_export_chat_impl` 处透传 |
| `exporter_core.py:3179` | `_export_all_chats_impl(...)` 签名加 `since/until` |
| `exporter_core.py:3330` / `3395` | `export_all_chats()` / `export_chat()` 公开签名加 `since/until` |
| `exporter_core.py` 目录命名 | 窗口导出时目录名追加后缀（如 `_20261025-20261101`），否则会覆盖全量结果 |
| `cli.py` | 加 `--since` / `--until` / `--last-days`，互斥；`--last-days` 换算为 `until=now, since=now-N天` |
| `app.py` | GUI 加「最近 N 天」输入框 + 起止日期（可选） |

**预计 ~70 行**，其中核心 SQL 改动不到 10 行。

---

## 五、剩余风险

| 风险 | 说明 | 缓解 |
|---|---|---|
| WAL 活跃导致重建 | 微信持续收消息时，每次 `_open('message_1')` 可能重建 3.4 s。批量 741 会话若频繁触发，会显著拖慢 | 实测确认触发频率；必要时批量内复用同一连接（需改 `load_rows` 生命周期，属独立优化） |
| `until=now` 漏最后几条 | 导出启动到结束之间新到的消息不在窗口内 | `--last-days` 用 `until=None`（无上界），或 `now + 1 天` |
| 窗口内消息为 0 | 走 `EmptyConversationError` → `skipped_empty`，语义是「没有消息」而非「窗口内没有」 | 索引文案改为「窗口内无消息」，或加 `window_empty` 状态 |
| 边界秒的 8 条消息 | 同秒最多 8 条，秒级边界会把整秒纳入/排除 | 符合预期；文档说明精度为秒 |
| 引用回复断裂 | 被引用消息在窗口外时正文仍保留引用文字，但原消息缺失 | 文档注明 |
| 上游私有 API | 本次新增不引入新依赖，仍只用到已有 19 个私有符号 | 顺手补齐 CI 契约断言 |

---

## 六、附：实验脚本已清理

- `%TEMP%\wechat-chat-export-sensitive\run-*` 三个实验遗留目录已删除
- 临时校准脚本已删除，仓库无残留文件（本文件除外）
- `clear_current_sensitive_cache()` 对「刚 close 仍被占用」的目录会保守跳过（`skipped`），属预期行为，非缺陷

---

## 七、实现与验证（2026-11-01）

按修正后的方案 B 落地，实际改动比预估更集中。

### 改动清单

| 文件 | 改动 |
|---|---|
| `exporter_core.py` | 新增 `parse_time_bound()`、`build_window_suffix()`、`_describe_window()`；`load_rows()` 增加 `since/until` 与动态 WHERE + `ORDER BY sort_seq`；`_export_chat_impl` / `_export_all_chats_impl` / `export_chat` / `export_all_chats` 透传窗口参数；目录名追加窗口后缀；JSON 顶层写 `time_window`；批量索引写窗口行 |
| `cli.py` | 新增 `--last-days` / `--since` / `--until` 与互斥校验；`--last-days` 换算为 `since=now-N天, until=None`；捕获 `ValueError` / `EmptyConversationError` 后友好提示并以 2 退出 |
| `app.py` | 新增「时间范围：最近 __ 天」输入框与 `_window_args()` 校验；`worker` / `worker_all` 透传 |
| `tests/test_time_window.py` | 新增 22 个用例（时间解析、后缀、窗口边界、同秒多条、缺列降级） |
| `README.md` | 新增「只导出最近一段时间」章节 |

顺带修掉一个窗口引入的隐患：批量索引原先用 `_stable_batch_folder()` 的名字拼链接，加了后缀后会指向不存在的目录；现在改为回填 `Path(output_dir).name`。

### 实测结果

| 验证项 | 结果 |
|---|---|
| 单会话窗口导出（2026-03-01 ~ 04-15） | 323 条，与全量过滤**逐条一致**（`local_id` 集合与顺序均相同，内容零差异） |
| 全量导出回归 | 4710 条 = `message_0` 4044 + `message_1` 666，与校准时分片行数完全吻合；JSON 不含 `time_window` |
| `--last-days 7`（带图片文件） | 32 条，图片 5/5、文件 4/4；首条在下界之后，末条为 14.8 小时前（含 WAL 内最新消息） |
| 媒体收敛 | 图片请求 379 → 5、文件 132 → 4，落盘数量一致 |
| 批量 `--all --last-days 7 --limit 3` | 22527 条，3/3 成功、0 失败，耗时 3 分 56 秒（含图片） |
| 批量索引链接 | 3/3 指向真实目录，目录名含 `_202610251326-open` 后缀 |
| 空窗口 | `会话B 2026-02-01~03-01` 返回 0 条，提示「时间窗口 … 内没有消息」，退出码 2 |
| 参数校验 | `--last-days` 与 `--since/--until` 互斥、负数、时间倒置均被拦截 |
| 单元测试 | 74 项全通过（原 52 + 新增 22） |
| GUI 冒烟 | 控件构建正常；填 7 → 距今 7.0 天；填 0.5 → 12 小时；`abc`/`0`/`-3` 均给出中文提示 |

### 与校准结论的偏差

无。三处修正（只用 `sort_seq`、放弃分片剪枝、精度到秒）全部落实，实现中未出现新的阻塞项。

### 遗留

- `--last-days` 在批量下每个会话复用同一 `since`，各会话窗口完全一致，符合预期；
- 索引表格的「最近消息」列仍是会话全库最近时间，不是窗口内时间，暂未改（属会话元信息）；
- GUI 只提供「最近 N 天」，`--since/--until` 的任意区间仍走命令行。

### v1.5.0 追加变更（实现与本文的差异）

- 窗口 SQL 不再使用 `ORDER BY sort_seq`（实测会多一步 `USE TEMP B-TREE`）；排序统一由 `load_rows` 末尾的 Python 侧完成，结果不变。
- 存在 NULL `sort_seq` 的分片会用 `IS NULL LIMIT 1` 真探测，命中才加括号包裹的 `OR sort_seq IS NULL`，NULL 行按 `create_time` 兜底（时间缺失则跳过），不再静默丢行。
- 索引的「最近消息」列在窗口模式已改名「会话最近消息」并附说明，「无消息」在窗口模式改为「窗口内无消息」。

