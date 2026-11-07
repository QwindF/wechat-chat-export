# -*- coding: utf-8 -*-
"""GUI 会话扫描选择器：list_chats 扫描、only_usernames 过滤与范围日志测试。"""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]


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
            "_picker_tests_exporter_core", ROOT / "exporter_core.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


def make_chats():
    """三条按最近消息降序排列的候选会话（与 _batch_chat_candidates 口径一致）。"""
    return [
        {"username": "wxid_a", "name": "甲", "is_group": False, "last_time": 300},
        {"username": "111@chatroom", "name": "群", "is_group": True, "last_time": 200},
        {"username": "wxid_b", "name": "乙", "is_group": False, "last_time": 100},
    ]


class ChatPickerTestBase(unittest.TestCase):
    module = None

    @classmethod
    def setUpClass(cls):
        cls.module = load_module()


class TestNormalizeOnlyUsernames(ChatPickerTestBase):
    """only_usernames 归一化：参数性质错误必须与「会话未发现」区分开。"""

    def test_none_returns_none(self):
        self.assertIsNone(self.module._normalize_only_usernames(None))

    def test_bare_string_rejected(self):
        # 防 set("wxid_a") 拆成字符集后把类型错误伪装成「未发现」。
        with self.assertRaises(ValueError) as cm:
            self.module._normalize_only_usernames("wxid_a")
        self.assertIn(
            "请传入 username 的列表/集合，而不是单个字符串",
            str(cm.exception),
        )

    def test_empty_containers_rejected(self):
        for empty in (set(), [], ()):
            with self.assertRaises(ValueError) as cm:
                self.module._normalize_only_usernames(empty)
            self.assertIn("所选会话列表为空", str(cm.exception))

    def test_non_string_element_rejected(self):
        with self.assertRaises(ValueError) as cm:
            self.module._normalize_only_usernames(["wxid_a", 123])
        message = str(cm.exception)
        self.assertIn("非法元素", message)
        self.assertIn("123", message)

    def test_empty_string_element_rejected(self):
        with self.assertRaises(ValueError) as cm:
            self.module._normalize_only_usernames({"wxid_a", ""})
        message = str(cm.exception)
        self.assertIn("非法元素", message)
        self.assertIn("非空字符串", message)

    def test_valid_list_returns_set(self):
        result = self.module._normalize_only_usernames(
            ["wxid_a", "wxid_b", "wxid_a"]
        )
        self.assertEqual(result, {"wxid_a", "wxid_b"})


class TestFilterChatsByUsernames(ChatPickerTestBase):
    """按 username 精确过滤：命中 / 部分未命中 / 全未命中三类。"""

    def test_all_hit_keeps_recency_order(self):
        chats = make_chats()
        kept, missed = self.module._filter_chats_by_usernames(
            chats, {"wxid_b", "111@chatroom"}
        )
        self.assertEqual(
            [item["username"] for item in kept], ["111@chatroom", "wxid_b"]
        )
        self.assertEqual(missed, 0)
        # 不修改入参。
        self.assertEqual(len(chats), 3)

    def test_partial_miss_is_counted(self):
        kept, missed = self.module._filter_chats_by_usernames(
            make_chats(), {"wxid_a", "wxid_ghost"}
        )
        self.assertEqual([item["username"] for item in kept], ["wxid_a"])
        self.assertEqual(missed, 1)

    def test_all_missed_returns_empty_and_count(self):
        kept, missed = self.module._filter_chats_by_usernames(
            make_chats(), {"wxid_x", "wxid_y"}
        )
        self.assertEqual(kept, [])
        self.assertEqual(missed, 2)


class TestBatchScopeSummary(ChatPickerTestBase):
    """范围日志三分支：发现 / 选中 / 数量上限的组合判定。"""

    def test_full_mode_without_limit(self):
        messages = self.module._batch_scope_summary(758, None, False, 758)
        self.assertEqual(messages, ["共发现 758 个可可靠识别的本地会话。"])

    def test_subset_without_limit_has_no_limit_wording(self):
        messages = self.module._batch_scope_summary(758, 3, False, 3)
        self.assertEqual(
            messages,
            ["共发现 758 个可可靠识别的本地会话，本次导出选中的 3 个。"],
        )
        self.assertFalse(any("数量上限" in m for m in messages))

    def test_subset_with_limit_reports_both(self):
        messages = self.module._batch_scope_summary(758, 30, True, 10)
        self.assertTrue(any("本次导出选中的 30 个" in m for m in messages))
        self.assertTrue(
            any("已按数量上限只处理最近的 10 个会话。" in m for m in messages)
        )

    def test_full_mode_with_limit_matches_legacy_wording(self):
        # 回归锚点：全量 + limit 只报数量上限一条，与现状一致。
        messages = self.module._batch_scope_summary(758, None, True, 100)
        self.assertEqual(messages, ["已按数量上限只处理最近的 100 个会话。"])


class TestExportAllChatsSubset(ChatPickerTestBase):
    """_export_all_chats_impl 的子集过滤与 limited 解耦端到端判定。"""

    def _run_impl(self, only_usernames=None, limit=None):
        chats = [
            {"username": f"wxid_{i}", "name": f"会话{i}", "is_group": False,
             "last_time": 100 - i}
            for i in range(3)
        ]
        logs = []

        def fake_impl(**kwargs):
            return {
                "chat_name": kwargs["contact"]["name"],
                "is_group": False,
                "message_count": 1,
                "sender_resolution_counts": {"resolved": 1},
                "media_stats": {"images_requested": 0, "images_exported": 0},
                "output_dir": str(self.out),
                "txt": str(self.out / "t.txt"),
                "md": str(self.out / "t.md"),
                "json": str(self.out / "t.json"),
            }

        with (
            patch.object(self.module, "WeChatDB", return_value=object()),
            patch.object(
                self.module, "_batch_chat_candidates",
                return_value=(chats, 0),
            ),
            patch.object(
                self.module, "_export_chat_impl", side_effect=fake_impl,
            ),
            tempfile.TemporaryDirectory() as out_dir,
        ):
            self.out = Path(out_dir)
            result = self.module._export_all_chats_impl(
                out_root=self.out,
                progress=logs.append,
                limit=limit,
                only_usernames=only_usernames,
            )
        return result, logs

    def test_subset_without_limit_no_truncation_wording(self):
        # 子集 3 个、无 limit：只报「选中的」，不出现「数量上限」。
        result, logs = self._run_impl(only_usernames={"wxid_0", "wxid_1", "wxid_2"})
        self.assertFalse(result["limited"])
        self.assertTrue(any("本次导出选中的 3 个" in m for m in logs))
        self.assertFalse(any("数量上限" in m for m in logs))

    def test_subset_with_limit_reports_selected_and_limit(self):
        # 子集 3 个 + limit=1：两条日志都有；limited 为真。
        result, logs = self._run_impl(
            only_usernames={"wxid_0", "wxid_1", "wxid_2"}, limit=1,
        )
        self.assertTrue(result["limited"])
        self.assertTrue(any("本次导出选中的 3 个" in m for m in logs))
        self.assertTrue(any("已按数量上限只处理最近的 1 个会话。" in m for m in logs))

    def test_all_missed_raises_value_error(self):
        with self.assertRaises(ValueError) as cm:
            self._run_impl(only_usernames={"wxid_ghost"})
        message = str(cm.exception)
        self.assertIn("1 个会话均未在本机发现", message)
        self.assertIn("共扫描 3 个本地会话", message)

    def test_partial_miss_logs_ignored_line(self):
        result, logs = self._run_impl(only_usernames={"wxid_0", "wxid_ghost"})
        self.assertFalse(result["limited"])
        self.assertTrue(
            any("有 1 个所选会话未在本机发现，已忽略。" in m for m in logs)
        )
        self.assertEqual(result["selected_total"], 1)

    def test_full_mode_with_limit_keeps_legacy_semantics(self):
        # 回归锚点：全量 + limit 仍截断、meta 三个字段与现状一致。
        result, logs = self._run_impl(limit=1)
        self.assertTrue(result["limited"])
        self.assertEqual(result["discovered_total"], 3)
        self.assertEqual(result["selected_total"], 1)
        self.assertTrue(any("已按数量上限只处理最近的 1 个会话。" in m for m in logs))

    def test_export_all_chats_rejects_bare_string(self):
        with self.assertRaises(ValueError) as cm:
            self.module.export_all_chats(only_usernames="wxid_a")
        self.assertIn(
            "请传入 username 的列表/集合，而不是单个字符串",
            str(cm.exception),
        )


class TestSortChatsByRecency(ChatPickerTestBase):
    """list_chats 排序：降序、无 last_time 稳定排后、不改动入参。"""

    def test_mixed_last_time_descending(self):
        chats = [
            {"username": "wxid_none1", "name": "无时间1", "is_group": False,
             "last_time": None},
            {"username": "wxid_old", "name": "旧", "is_group": False,
             "last_time": 100},
            {"username": "wxid_zero", "name": "零", "is_group": False,
             "last_time": 0},
            {"username": "wxid_new", "name": "新", "is_group": False,
             "last_time": 300},
            {"username": "wxid_none2", "name": "无时间2", "is_group": False,
             "last_time": None},
        ]
        ordered = self.module._sort_chats_by_recency(chats)
        self.assertEqual(
            [item["username"] for item in ordered],
            ["wxid_new", "wxid_old", "wxid_none1", "wxid_zero", "wxid_none2"],
        )
        # 不改动入参列表的原始顺序。
        self.assertEqual(
            [item["username"] for item in chats],
            ["wxid_none1", "wxid_old", "wxid_zero", "wxid_new", "wxid_none2"],
        )

    def test_missing_last_time_order_is_stable(self):
        chats = [
            {"username": username, "name": username, "is_group": False,
             "last_time": None}
            for username in ("wxid_b", "wxid_a", "wxid_c")
        ]
        ordered = self.module._sort_chats_by_recency(chats)
        self.assertEqual(
            [item["username"] for item in ordered],
            ["wxid_b", "wxid_a", "wxid_c"],
        )


class TestListChats(ChatPickerTestBase):
    """list_chats 沙箱生命周期与 db_dir 归一化（P0-4 / P1）。"""

    def setUp(self):
        self.candidates = [
            {"username": "wxid_none", "name": "无时间", "is_group": False,
             "last_time": None},
            {"username": "wxid_old", "name": "旧", "is_group": False,
             "last_time": 100},
            {"username": "wxid_new", "name": "新", "is_group": False,
             "last_time": 300},
        ]

    def test_returns_recency_sorted_list_and_cleans_workdir(self):
        logs = []
        with tempfile.TemporaryDirectory() as td:
            with (
                patch.object(
                    self.module.tempfile, "gettempdir", return_value=td,
                ),
                patch.object(self.module, "WeChatDB", return_value=object()),
                patch.object(
                    self.module, "_batch_chat_candidates",
                    return_value=(self.candidates, 0),
                ),
            ):
                chats = self.module.list_chats(progress=logs.append)
            # 正常路径结束后不留 run-* 敏感临时目录。
            residue = list(
                (Path(td) / "wechat-chat-export-sensitive").glob("run-*")
            )
            self.assertEqual(residue, [])
        self.assertEqual(
            [item["username"] for item in chats],
            ["wxid_new", "wxid_old", "wxid_none"],
        )
        self.assertTrue(any("正在扫描" in m for m in logs))

    def test_db_dir_is_resolved_before_connecting(self):
        with tempfile.TemporaryDirectory() as td:
            with (
                patch.object(
                    self.module.tempfile, "gettempdir", return_value=td,
                ),
                patch.object(
                    self.module, "resolve_db_dir", return_value="D:/resolved",
                ) as resolver,
                patch.object(self.module, "WeChatDB", return_value=object()) as ctor,
                patch.object(
                    self.module, "_batch_chat_candidates",
                    return_value=(self.candidates, 0),
                ),
            ):
                self.module.list_chats(db_dir="E:/原始目录")
            # 原始目录先经 resolve_db_dir 归一化，再传给 WeChatDB。
            resolver.assert_called_once_with("E:/原始目录")
            self.assertEqual(ctor.call_args.kwargs["db_dir"], "D:/resolved")

    def test_db_dir_none_skips_resolver(self):
        with tempfile.TemporaryDirectory() as td:
            with (
                patch.object(
                    self.module.tempfile, "gettempdir", return_value=td,
                ),
                patch.object(self.module, "resolve_db_dir") as resolver,
                patch.object(self.module, "WeChatDB", return_value=object()) as ctor,
                patch.object(
                    self.module, "_batch_chat_candidates",
                    return_value=(self.candidates, 0),
                ),
            ):
                self.module.list_chats()
            resolver.assert_not_called()
            self.assertIsNone(ctor.call_args.kwargs["db_dir"])

    def test_cleanup_still_runs_when_db_connection_fails(self):
        # P1 硬要求：WeChatDB 构造抛异常时，清理仍被调用且异常上抛。
        cleanup_workdirs = []
        original_cleanup = self.module._cleanup_sensitive_workdir

        def spy_cleanup(workdir, progress=None):
            cleanup_workdirs.append(Path(workdir))
            return original_cleanup(workdir, progress=progress)

        with tempfile.TemporaryDirectory() as td:
            with (
                patch.object(
                    self.module.tempfile, "gettempdir", return_value=td,
                ),
                patch.object(
                    self.module, "WeChatDB",
                    Mock(side_effect=RuntimeError("微信未运行")),
                ),
                patch.object(
                    self.module, "_cleanup_sensitive_workdir",
                    side_effect=spy_cleanup,
                ),
            ):
                with self.assertRaises(RuntimeError):
                    self.module.list_chats()
            residue = list(
                (Path(td) / "wechat-chat-export-sensitive").glob("run-*")
            )
        self.assertEqual(len(cleanup_workdirs), 1)
        # 真实清理也完成了，无 run-* 残留。
        self.assertFalse(cleanup_workdirs[0].exists())
        self.assertEqual(residue, [])


if __name__ == "__main__":
    unittest.main()
