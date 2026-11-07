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
