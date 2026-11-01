# -*- coding: utf-8 -*-
"""时间窗口导出（--since/--until/--last-days）的取值与边界测试。"""
import hashlib
import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
USERNAME = "wxid_window_target"
TABLE = "Msg_" + hashlib.md5(USERNAME.encode("utf-8")).hexdigest()
# 与 exporter_core._MAX_SUPPORTED_TS 保持一致：2100-01-01 08:00（UTC+8）。
_MAX_TS = 4102444800

COLUMNS = (
    "local_id", "local_type", "server_id", "real_sender_id", "create_time",
    "message_content", "source", "compress_content", "packed_info_data",
    "sort_seq",
)

# (local_id, create_time 秒, 同秒序号) —— 1000s 故意放 3 条，模拟同秒多条消息。
ROWS = [
    (1, 999, 0),
    (2, 1000, 0),
    (3, 1000, 1),
    (4, 1000, 2),
    (5, 1001, 0),
    (6, 1002, 0),
    (7, 1005, 0),
]


def load_module():
    wechatauto = ModuleType("wechatauto")
    wechatauto.WeChatDB = Mock(side_effect=AssertionError("禁止真实微信库"))
    wechatauto.MediaDownloader = Mock(side_effect=AssertionError("禁止真实媒体"))
    zstandard = ModuleType("zstandard")
    zstandard.ZstdDecompressor = Mock(side_effect=AssertionError("无压缩夹具"))
    pillow = ModuleType("PIL")
    pillow.Image = Mock()
    pillow.ImageStat = Mock()
    pillow.ImageTk = Mock()
    with patch.dict(sys.modules, {
        "wechatauto": wechatauto, "zstandard": zstandard, "PIL": pillow,
    }):
        spec = importlib.util.spec_from_file_location(
            "_window_tests_exporter_core", ROOT / "exporter_core.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class FakeDB:
    """只实现 load_rows 用到的两个方法，连接指向临时 sqlite 文件。"""

    def __init__(self, db_path):
        self.db_path = db_path

    def _message_dbs(self):
        return ["message/message_0.db"]

    def _open(self, rel):
        return sqlite3.connect(self.db_path)


class WindowTestBase(unittest.TestCase):
    module = None

    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "message_0.db")
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            f"CREATE TABLE {TABLE} ({', '.join(COLUMNS)})"
        )
        conn.executemany(
            f"INSERT INTO {TABLE} VALUES (?, 1, ?, NULL, ?, '', 0, NULL, NULL, ?)",
            [
                (lid, 100 + lid, ct, ct * 1000 + seq)
                for lid, ct, seq in ROWS
            ],
        )
        conn.commit()
        conn.close()
        self.db = FakeDB(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def load(self, since=None, until=None):
        return self.module.load_rows(self.db, USERNAME, since=since, until=until)

    def ids(self, since=None, until=None):
        return [r["local_id"] for r in self.load(since, until)]


class TestParseTimeBound(WindowTestBase):
    def test_none(self):
        self.assertIsNone(self.module.parse_time_bound(None))

    def test_blank_string(self):
        self.assertIsNone(self.module.parse_time_bound("   "))

    def test_date_only(self):
        self.assertEqual(
            self.module.parse_time_bound("2026-10-25"),
            int(datetime(2026, 10, 25).timestamp()),
        )

    def test_date_and_time(self):
        self.assertEqual(
            self.module.parse_time_bound("2026-10-25 08:30"),
            int(datetime(2026, 10, 25, 8, 30).timestamp()),
        )

    def test_datetime_object(self):
        value = datetime(2026, 10, 25, 8, 30)
        self.assertEqual(self.module.parse_time_bound(value), int(value.timestamp()))

    def test_seconds_int(self):
        self.assertEqual(self.module.parse_time_bound(1793400000), 1793400000)

    def test_milliseconds_are_normalised(self):
        self.assertEqual(self.module.parse_time_bound(1793400000123), 1793400000)

    def test_bad_string_raises(self):
        for bad in ("2026/10/25", "abc"):
            with self.assertRaises(ValueError):
                self.module.parse_time_bound(bad)

    def test_bool_raises(self):
        with self.assertRaises(ValueError):
            self.module.parse_time_bound(True)


class TestWindowSuffix(WindowTestBase):
    def test_no_window_has_no_suffix(self):
        self.assertEqual(self.module.build_window_suffix(None, None), "")

    def test_open_ended(self):
        since = int(datetime(2026, 10, 25).timestamp())
        self.assertEqual(self.module.build_window_suffix(since, None), "_20261025-open")
        self.assertEqual(self.module.build_window_suffix(None, since), "_open-20261025")

    def test_full_window(self):
        since = int(datetime(2026, 10, 25).timestamp())
        until = int(datetime(2026, 11, 1).timestamp())
        self.assertEqual(
            self.module.build_window_suffix(since, until), "_20261025-20261101"
        )

    def test_same_day_different_hour_does_not_collide(self):
        day = int(datetime(2026, 10, 25).timestamp())
        later = int(datetime(2026, 10, 25, 13, 24).timestamp())
        self.assertNotEqual(
            self.module.build_window_suffix(day, None),
            self.module.build_window_suffix(later, None),
        )


class TestLoadRowsWindow(WindowTestBase):
    def test_no_window_reads_everything(self):
        self.assertEqual(self.ids(), [1, 2, 3, 4, 5, 6, 7])

    def test_since_is_inclusive(self):
        self.assertEqual(self.ids(since=1001), [5, 6, 7])

    def test_until_is_exclusive(self):
        self.assertEqual(self.ids(until=1001), [1, 2, 3, 4])

    def test_both_bounds(self):
        self.assertEqual(self.ids(since=1000, until=1002), [2, 3, 4, 5])

    def test_same_second_rows_are_kept_together(self):
        # 1000 秒内的 3 条消息必须整体包含，不能被秒级边界切掉。
        rows = self.load(since=1000, until=1001)
        self.assertEqual([r["local_id"] for r in rows], [2, 3, 4])
        self.assertEqual({r["sort_seq"] for r in rows}, {1000000, 1000001, 1000002})

    def test_empty_window_returns_empty_list(self):
        self.assertEqual(self.ids(since=2000, until=3000), [])

    def test_window_keeps_rows_sorted(self):
        rows = self.load(since=1000)
        seqs = [r["sort_seq"] for r in rows]
        self.assertEqual(seqs, sorted(seqs))

    def test_missing_sort_seq_column_raises(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("DROP TABLE " + TABLE)
        conn.execute(
            f"CREATE TABLE {TABLE} (local_id INTEGER, local_type INTEGER, create_time INTEGER)"
        )
        conn.commit()
        conn.close()
        with self.assertRaises(ValueError):
            self.load(since=1000)

    def test_missing_sort_seq_column_ok_without_window(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("DROP TABLE " + TABLE)
        conn.execute(
            f"CREATE TABLE {TABLE} (local_id INTEGER, local_type INTEGER, create_time INTEGER)"
        )
        conn.execute(f"INSERT INTO {TABLE} VALUES (42, 1, 1000)")
        conn.commit()
        conn.close()
        self.assertEqual(self.ids(), [42])


class TestParseTimeBoundRange(WindowTestBase):
    """数值/日期范围校验：返回值必须能被 fromtimestamp 表示。"""

    def test_non_finite_numbers_rejected(self):
        for bad in (float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                self.module.parse_time_bound(bad)

    def test_huge_number_rejected(self):
        # 数值分支不经过 timestamp()，必须靠范围校验拦下，
        # 否则 1e27 秒会一路带到 build_window_suffix 才炸 OverflowError。
        with self.assertRaises(ValueError):
            self.module.parse_time_bound(1e30)

    def test_upper_bound_exceeded_rejected(self):
        with self.assertRaises(ValueError):
            self.module.parse_time_bound(_MAX_TS + 1)

    def test_boundaries_accepted(self):
        self.assertEqual(self.module.parse_time_bound(0), 0)
        self.assertEqual(self.module.parse_time_bound(_MAX_TS), _MAX_TS)

    def test_out_of_range_dates_rejected(self):
        # 1900/9999 在 Windows 上抛 OSError；1800 越过负 epoch 边界；
        # 1970-01-02 在 UTC+8 是负 epoch。平台差异必须被统一成 ValueError。
        for bad in ("1900-01-01", "9999-12-31", "1970-01-02", datetime(1800, 1, 1)):
            with self.assertRaises(ValueError):
                self.module.parse_time_bound(bad)


class TestLastDaysWindow(WindowTestBase):
    def test_valid_days(self):
        for days in (7, 0.5):
            result = self.module.last_days_window(days)
            self.assertIsNone(result["until"])
            expected = datetime.now() - timedelta(days=days)
            self.assertLess(abs((result["since"] - expected).total_seconds()), 5)

    def test_non_numeric_or_non_positive_rejected(self):
        for bad in (float("inf"), float("nan"), "abc", 0, -1):
            with self.assertRaises(ValueError):
                self.module.last_days_window(bad)

    def test_timedelta_overflow_rejected(self):
        with self.assertRaises(ValueError):
            self.module.last_days_window(1e9)

    def test_result_out_of_range_rejected(self):
        # 30000 天本身是合法 timedelta，但 since≈1944 年，超出支持范围。
        with self.assertRaises(ValueError):
            self.module.last_days_window(30000)


class TestWindowSuffixApplication(WindowTestBase):
    """后缀拼接：先截断基础名，保证后缀与 [digest] 不被 100 字符上限吃掉。"""

    def test_suffix_survives_long_name(self):
        result = self.module._apply_window_suffix("x" * 100, "_20261025-open")
        self.assertLessEqual(len(result), 100)
        self.assertTrue(result.endswith("_20261025-open"))

    def test_no_suffix_returns_name_unchanged(self):
        self.assertEqual(self.module._apply_window_suffix("abc", ""), "abc")

    def test_empty_name_falls_back(self):
        result = self.module._apply_window_suffix("", "_20261025-open")
        self.assertTrue(result.startswith("未命名会话"))
        self.assertTrue(result.endswith("_20261025-open"))

    def test_different_windows_produce_different_dirs(self):
        a = self.module._apply_window_suffix("x" * 100, "_20261025-open")
        b = self.module._apply_window_suffix("x" * 100, "_20261026-open")
        self.assertNotEqual(a, b)

    def test_long_name_window_dir_differs_from_full_export(self):
        name = "x" * 100
        full = self.module.safe_folder_name(name)
        windowed = self.module.safe_folder_name(
            self.module._apply_window_suffix(name, "_20261025-open")
        )
        self.assertNotEqual(full, windowed)

    def test_stable_batch_folder_keeps_digest_with_suffix(self):
        username = "wxid_" + "a" * 81  # 86 字符，超过 100-14 的旧阈值
        result = self.module._stable_batch_folder(username, "_20261025-open")
        self.assertLessEqual(len(result), 100)
        self.assertTrue(result.endswith("_20261025-open"))
        # digest 必须完整保留，不能被后缀挤掉。
        self.assertRegex(result, r" \[[0-9a-f]{10}\]")

    def test_stable_batch_folder_without_suffix_unchanged_shape(self):
        username = "wxid_" + "a" * 81
        result = self.module._stable_batch_folder(username)
        self.assertLessEqual(len(result), 99)
        self.assertRegex(result, r" \[[0-9a-f]{10}\]$")


class TestNullSortSeq(WindowTestBase):
    """NULL sort_seq：真探测、括号包裹的 OR、create_time 兜底与排序。"""

    def add_null_rows(self):
        # (local_id, server_id, create_time)，sort_seq 列全部为 NULL。
        conn = sqlite3.connect(self.db_path)
        conn.executemany(
            f"INSERT INTO {TABLE} VALUES (?, 1, ?, NULL, ?, '', 0, NULL, NULL, NULL)",
            [
                (10, 110, 1000),  # 窗口内，应按 create_time 兜底保留
                (11, 111, 2000),  # 窗口外，应排除
                (12, 112, None),  # create_time 缺失，应排除
            ],
        )
        conn.commit()
        conn.close()

    def test_has_null_sort_seq_detection(self):
        conn = sqlite3.connect(self.db_path)
        try:
            self.assertFalse(self.module._has_null_sort_seq(conn, TABLE))
        finally:
            conn.close()
        self.add_null_rows()
        conn = sqlite3.connect(self.db_path)
        try:
            self.assertTrue(self.module._has_null_sort_seq(conn, TABLE))
        finally:
            conn.close()

    def test_null_rows_kept_or_skipped_by_create_time(self):
        self.add_null_rows()
        stats = {}
        rows = self.module.load_rows(
            self.db, USERNAME, since=999, until=1006, stats=stats
        )
        ids = [r["local_id"] for r in rows]
        self.assertIn(10, ids)       # 窗口内的 NULL 行被兜底保留
        self.assertNotIn(11, ids)    # 窗口外
        self.assertNotIn(12, ids)    # create_time 缺失
        self.assertEqual(stats["null_sort_seq_rows"], 1)
        self.assertEqual(stats["null_sort_seq_skipped"], 2)

    def test_null_row_sorted_by_create_time_not_first(self):
        self.add_null_rows()
        ids = self.ids(since=999, until=1006)
        # local_id=10 的 create_time=1000，排序键 1000000 与 local_id=2 相同，
        # 应落在 [1, 2, 10, 3, ...]，而不是被 (None or 0) 顶到最前面。
        self.assertEqual(ids, [1, 2, 10, 3, 4, 5, 6, 7])

    def test_stats_optional(self):
        self.add_null_rows()
        rows = self.module.load_rows(self.db, USERNAME, since=999, until=1006)
        self.assertIn(10, [r["local_id"] for r in rows])

    def _spy_execute(self):
        """返回连接代理捕获所有 SQL 文本；用例结束自动还原 _open。"""
        captured = []
        original_open = self.db._open

        class SpyConnection:
            # sqlite3.Connection 的属性是只读的，不能直接打补丁，
            # 用代理对象拦截 execute，其余全部透传。
            def __init__(self, conn):
                self._conn = conn

            def execute(self, sql, *args, **kwargs):
                captured.append(sql)
                return self._conn.execute(sql, *args, **kwargs)

            def close(self):
                self._conn.close()

            def __getattr__(self, name):
                return getattr(self._conn, name)

        def spy_open(rel):
            return SpyConnection(original_open(rel))

        self.db._open = spy_open
        self.addCleanup(lambda: setattr(self.db, "_open", original_open))
        return captured

    def test_no_null_keeps_plain_sql(self):
        captured = self._spy_execute()
        rows = self.load(since=1000, until=1002)
        window_sql = [s for s in captured if "sort_seq >= ?" in s]
        self.assertTrue(window_sql, "应当执行窗口过滤查询")
        for sql in window_sql:
            self.assertNotIn("OR sort_seq IS NULL", sql)
            self.assertNotIn("ORDER BY", sql)
        # 与既有 test_both_bounds 口径一致：[1000s, 1002s) 含 1000s 三条 + 1001s 一条。
        self.assertEqual([r["local_id"] for r in rows], [2, 3, 4, 5])

    def test_null_adds_parenthesised_or_clause(self):
        self.add_null_rows()
        captured = self._spy_execute()
        self.module.load_rows(self.db, USERNAME, since=1000, until=1002)
        main_sql = [s for s in captured if "OR sort_seq IS NULL" in s]
        self.assertTrue(main_sql, "存在 NULL 时应追加 OR sort_seq IS NULL")
        for sql in main_sql:
            self.assertIn("(sort_seq >= ? AND sort_seq < ?) OR sort_seq IS NULL", sql)


class TestAllChatsIndexWording(WindowTestBase):
    """索引文案：窗口模式与全量模式各说各话。"""

    def _write_index(self, meta, error=None):
        chats = [
            {
                "name": "会话A",
                "username": "wxid_a",
                "is_group": False,
                "last_time": 1793400000,
                "last_time_text": "2026-10-25 10:00",
                "folder": "wxid_a [abc123def0]",
                "status": "skipped_empty",
                "message_count": 0,
                "error": error
                or "时间窗口 2026-10-25 00:00:00 ~ 2026-11-01 00:00:00 内没有消息。",
            },
        ]
        base_meta = {
            "generated_at": "2026-11-01 00:00:00",
            "discovered_total": 1,
            "unresolved_message_tables": 0,
            "selected_total": 1,
            "exported": 0,
            "skipped_empty": 1,
            "failed": 0,
            "total_messages": 0,
        }
        base_meta.update(meta)
        out_root = Path(self.tmp.name)
        json_path, md_path = self.module._write_all_chats_index(out_root, chats, base_meta)
        return md_path.read_text(encoding="utf-8")

    def test_windowed_index_wording(self):
        md = self._write_index({
            "time_window": {"since": "2026-10-25 00:00:00", "until": "2026-11-01 00:00:00"},
        })
        self.assertIn("窗口内无消息：1", md)
        self.assertIn("会话最近消息", md)
        self.assertIn("窗口内消息数", md)
        # 状态列复用 entry["error"] 的具体窗口文案。
        self.assertIn("时间窗口 2026-10-25 00:00:00 ~ 2026-11-01 00:00:00 内没有消息。", md)
        self.assertIn("「会话最近消息」来自会话表，可能晚于窗口结束。", md)
        # 旧的汇总行写法（；无消息：N）不应再出现。
        self.assertNotIn("；无消息：", md)

    def test_full_index_wording_unchanged(self):
        md = self._write_index({})
        self.assertIn("无消息：1", md)
        self.assertIn("最近消息", md)
        self.assertIn("消息数", md)
        self.assertNotIn("窗口内", md)

    def test_pipe_in_error_is_escaped(self):
        md = self._write_index(
            {"time_window": {"since": "2026-10-25 00:00:00", "until": None}},
            error="时间窗口 a | b 内没有消息。",
        )
        # 状态列出现 | 必须转义，否则会撑破 Markdown 表格。
        self.assertIn("时间窗口 a \\| b 内没有消息。", md)
