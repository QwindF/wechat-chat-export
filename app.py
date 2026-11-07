# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import os
import queue
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import psutil

from exporter_core import (
    clear_current_sensitive_cache,
    clear_sensitive_cache,
    export_all_chats,
    export_chat,
    install_local_asr_model,
    install_rust_silk,
    last_days_window,
    list_chats,
    local_asr_status,
    rust_silk_status,
)
from preview import open_chat_preview
from wechat_data_dirs import choose_wechat_data_dir

APP_TITLE = "微信聊天导出给大模型"
WECHAT_PROCESS_NAMES = {"weixin.exe", "wechat.exe"}

# 与 EXE 文件图标使用同一套图形。
WINDOW_ICON_PNG_BASE64 = """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"""


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def is_wechat_running() -> bool:
    """检测 Windows 微信是否正在运行。"""
    try:
        for proc in psutil.process_iter(["name"]):
            name = (proc.info.get("name") or "").lower()
            if name in WECHAT_PROCESS_NAMES:
                return True
    except (psutil.Error, OSError):
        # 检测本身异常时不阻断导出，让底层给出真实错误。
        return True
    return False


class ChatPickerDialog(tk.Toplevel):
    """「选择要导出的会话」对话框：行选中高亮模型，username 集合是选中态唯一事实源。"""

    def __init__(self, parent, chats, on_confirm):
        super().__init__(parent)
        self.app = parent
        self.chats = chats
        self.on_confirm = on_confirm
        self._selected_usernames = set()
        # 重渲染 / 程序化改选中时 Treeview 也会发 <<TreeviewSelect>>，
        # 用该标志避免错误同步选中集合。
        self._syncing_selection = False

        self.title("选择要导出的会话")
        self.transient(parent)
        self.geometry("720x520")
        self.minsize(560, 380)

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        search_row = ttk.Frame(self, padding=(12, 10, 12, 4))
        search_row.grid(row=0, column=0, sticky="ew")
        search_row.grid_columnconfigure(1, weight=1)
        ttk.Label(search_row, text="搜索：").grid(row=0, column=0, sticky="w")
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_row, textvariable=self.search_var)
        self.search_entry.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        tree_frame = ttk.Frame(self, padding=(12, 4, 12, 4))
        tree_frame.grid(row=1, column=0, sticky="nsew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        columns = ("name", "type", "last_time")
        self.tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
        )
        self.tree.heading("name", text="会话名")
        self.tree.heading("type", text="类型")
        self.tree.heading("last_time", text="最近消息时间")
        self.tree.column("name", width=320, anchor="w")
        self.tree.column("type", width=70, anchor="center", stretch=False)
        self.tree.column("last_time", width=135, anchor="center", stretch=False)
        self.tree.grid(row=0, column=0, sticky="nsew")

        scroll = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.grid(row=0, column=1, sticky="ns")

        btn_row = ttk.Frame(self, padding=(12, 4, 12, 12))
        btn_row.grid(row=2, column=0, sticky="ew")
        self.select_all_btn = ttk.Button(
            btn_row, text="全选", command=self._on_select_all
        )
        self.select_all_btn.pack(side="left")
        self.invert_btn = ttk.Button(btn_row, text="反选", command=self._on_invert)
        self.invert_btn.pack(side="left", padx=(8, 0))
        self.rescan_btn = ttk.Button(
            btn_row, text="重新扫描", command=self._on_rescan
        )
        self.rescan_btn.pack(side="left", padx=(8, 0))
        self.cancel_btn = ttk.Button(btn_row, text="取消", command=self._on_cancel)
        self.cancel_btn.pack(side="right")
        self.ok_btn = ttk.Button(btn_row, text="确定", command=self._on_ok)
        self.ok_btn.pack(side="right", padx=(0, 8))

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.search_var.trace_add("write", self._on_search_changed)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self._render_list()
        self.grab_set()
        self.search_entry.focus_set()

    @staticmethod
    def _format_last_time(value):
        if isinstance(value, int) and value > 0:
            try:
                return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M")
            except (OverflowError, OSError, ValueError):
                return "—"
        return "—"

    def _visible_chats(self):
        """按搜索词过滤：匹配显示名或 username 的子串（大小写不敏感）。"""
        query = self.search_var.get().strip().casefold()
        if not query:
            return self.chats
        matched = []
        for chat in self.chats:
            name = (chat.get("name") or "").casefold()
            username = (chat.get("username") or "").casefold()
            if query in name or query in username:
                matched.append(chat)
        return matched

    def _render_list(self):
        """按当前过滤词重建可见行；iid 用 username，选中态按集合恢复高亮。"""
        self._syncing_selection = True
        try:
            self.tree.delete(*self.tree.get_children())
            selected_visible = []
            for chat in self._visible_chats():
                username = chat["username"]
                name = str(chat.get("name") or "").strip() or username
                chat_type = "群聊" if chat.get("is_group") else "私聊"
                self.tree.insert(
                    "",
                    "end",
                    iid=username,
                    values=(
                        name,
                        chat_type,
                        self._format_last_time(chat.get("last_time")),
                    ),
                )
                if username in self._selected_usernames:
                    selected_visible.append(username)
            if selected_visible:
                self.tree.selection_set(selected_visible)
        finally:
            self._syncing_selection = False

    def _on_tree_select(self, _event):
        if self._syncing_selection:
            return
        # iid 即 username，原生选中直接同步进唯一事实源集合。
        self._selected_usernames = set(self.tree.selection())

    def _on_search_changed(self, *_args):
        self._render_list()

    def _on_select_all(self):
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children)

    def _on_invert(self):
        current = set(self.tree.selection())
        inverted = [
            iid for iid in self.tree.get_children() if iid not in current
        ]
        if inverted:
            self.tree.selection_set(inverted)
        else:
            for iid in current:
                self.tree.selection_remove(iid)

    def _on_rescan(self):
        # 重新扫描期间禁用对话框内全部控件，完成后由主窗口恢复。
        self._set_controls_state("disabled")
        self.app._scan_chats_async(target=self)

    def _on_ok(self):
        if not self._selected_usernames:
            messagebox.showwarning(
                APP_TITLE,
                "请至少选择一个会话。",
                parent=self,
            )
            return
        usernames = set(self._selected_usernames)
        chats = self.chats
        self.destroy()
        if self.on_confirm:
            self.on_confirm(chats, usernames)

    def _on_cancel(self):
        # 取消与窗口关闭：销毁对话框，无任何导出副作用。
        self.destroy()

    def _set_controls_state(self, state):
        for widget in (
            self.search_entry,
            self.select_all_btn,
            self.invert_btn,
            self.rescan_btn,
            self.ok_btn,
            self.cancel_btn,
        ):
            widget.configure(state=state)
        # Treeview 不支持 configure(state=...)，要用 ttk 的 state 命令。
        if state == "disabled":
            self.tree.state(["disabled"])
        else:
            self.tree.state(["!disabled"])

    def refresh_chats(self, chats):
        """「重新扫描」完成后由主窗口调用：刷新列表并保持仍存在的选中态。"""
        self.chats = chats
        self._selected_usernames &= {
            chat["username"] for chat in chats
        }
        self._render_list()
        self._set_controls_state("normal")

    def on_scan_error(self):
        """「重新扫描」失败后由主窗口调用：恢复控件，保留原列表。"""
        self._set_controls_state("normal")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("920x730")
        self.minsize(820, 630)

        try:
            icon_bytes = base64.b64decode(WINDOW_ICON_PNG_BASE64)
            self._window_icon = tk.PhotoImage(data=icon_bytes)
            self.iconphoto(True, self._window_icon)
        except Exception:
            self._window_icon = None

        self.q = queue.Queue()
        self.last_output = None
        self.last_result = None
        # 导出前若触发 rust-silk / 语音模型安装，安装完成后按 mode 恢复对应入口。
        self.pending_mode = "single"
        self.pending_usernames = None
        # 会话扫描缓存：(微信数据目录原始输入, list_chats 结果)，仅存内存。
        self._scan_cache = None

        pad = ttk.Frame(self, padding=18)
        pad.grid(row=0, column=0, sticky="nsew")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        pad.grid_columnconfigure(0, weight=1)
        pad.grid_rowconfigure(10, weight=1)

        ttk.Label(
            pad,
            text="微信聊天信息 → 大模型可读 TXT / Markdown / JSON",
            font=("Microsoft YaHei UI", 16, "bold"),
        ).grid(row=0, column=0, sticky="w")

        tk.Label(
            pad,
            text="⚠ 使用前请先登录 Windows 微信，并保持微信在后台运行。",
            fg="#b45309",
            font=("Microsoft YaHei UI", 10, "bold"),
        ).grid(row=1, column=0, sticky="w", pady=(8, 2))

        ttk.Label(
            pad,
            text="支持私聊与群聊。输入准确备注名、昵称或群名；程序会自动识别。",
        ).grid(row=2, column=0, sticky="w", pady=(2, 16))

        row = ttk.Frame(pad)
        row.grid(row=3, column=0, sticky="ew")
        row.grid_columnconfigure(1, weight=1)

        ttk.Label(row, text="好友 / 群聊：").grid(row=0, column=0, sticky="w")
        self.name_var = tk.StringVar()
        self.entry = ttk.Entry(row, textvariable=self.name_var)
        self.entry.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        self.entry.bind("<Return>", lambda e: self.start_export())

        self.export_btn = ttk.Button(row, text="开始导出", command=self.start_export)
        self.export_btn.grid(row=0, column=2)

        self.export_all_btn = ttk.Button(
            row,
            text="导出全部聊天",
            command=self.start_export_all,
        )
        self.export_all_btn.grid(row=0, column=3, padx=(8, 0))

        self.scan_btn = ttk.Button(
            row,
            text="扫描选择…",
            command=self.start_scan_pick,
        )
        self.scan_btn.grid(row=0, column=4, padx=(8, 0))

        outrow = ttk.Frame(pad)
        outrow.grid(row=4, column=0, sticky="ew", pady=(12, 8))
        outrow.grid_columnconfigure(1, weight=1)

        ttk.Label(outrow, text="输出目录：").grid(row=0, column=0, sticky="w")
        self.out_var = tk.StringVar(value=str(app_dir() / "exports"))
        ttk.Entry(outrow, textvariable=self.out_var).grid(
            row=0, column=1, sticky="ew", padx=(8, 8)
        )
        ttk.Button(outrow, text="选择", command=self.choose_out).grid(row=0, column=2)

        dbrow = ttk.Frame(pad)
        dbrow.grid(row=5, column=0, sticky="ew", pady=(0, 8))
        dbrow.grid_columnconfigure(1, weight=1)

        ttk.Label(dbrow, text="微信数据目录：").grid(row=0, column=0, sticky="w")
        self.db_dir_var = tk.StringVar()
        ttk.Entry(dbrow, textvariable=self.db_dir_var).grid(
            row=0, column=1, sticky="ew", padx=(8, 8)
        )
        ttk.Button(dbrow, text="选择", command=self.choose_db_dir).grid(
            row=0, column=2
        )
        ttk.Label(
            dbrow,
            text="留空自动探测；点“选择”可列出本机发现的微信数据目录，也可手动浏览。",
            foreground="#6b7280",
        ).grid(row=1, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=(2, 0))

        media_row = ttk.Frame(pad)
        media_row.grid(row=6, column=0, sticky="ew", pady=(2, 2))
        ttk.Label(media_row, text="附带导出：").pack(side="left")

        self.images_var = tk.BooleanVar(value=True)
        self.files_var = tk.BooleanVar(value=True)
        self.voices_var = tk.BooleanVar(value=False)
        self.videos_var = tk.BooleanVar(value=False)
        self.transcribe_var = tk.BooleanVar(value=False)

        ttk.Checkbutton(
            media_row, text="图片", variable=self.images_var
        ).pack(side="left", padx=(6, 8))
        ttk.Checkbutton(
            media_row, text="文件", variable=self.files_var
        ).pack(side="left", padx=(0, 8))
        ttk.Checkbutton(
            media_row, text="语音", variable=self.voices_var
        ).pack(side="left", padx=(0, 8))
        ttk.Checkbutton(
            media_row, text="视频", variable=self.videos_var
        ).pack(side="left", padx=(0, 8))
        ttk.Checkbutton(
            media_row,
            text="语音转文字（本地）",
            variable=self.transcribe_var,
            command=self.on_transcribe_toggle,
        ).pack(side="left", padx=(0, 8))

        ttk.Label(
            pad,
            text="仅导出本机仍有缓存的附件；“语音转文字（本地）”默认关闭，勾选后会自动同时导出语音。",
        ).grid(row=8, column=0, sticky="w", pady=(2, 4))

        winrow = ttk.Frame(pad)
        winrow.grid(row=7, column=0, sticky="ew", pady=(4, 2))
        ttk.Label(winrow, text="时间范围：最近").pack(side="left")
        self.last_days_var = tk.StringVar(value="")
        ttk.Entry(winrow, textvariable=self.last_days_var, width=6).pack(
            side="left", padx=(4, 4)
        )
        ttk.Label(winrow, text="天").pack(side="left")
        ttk.Label(
            winrow,
            text="（留空 = 导出全部历史；填 7 即只导出最近 7 天，可带小数如 0.5）",
            foreground="#6b7280",
        ).pack(side="left", padx=(8, 0))

        ttk.Separator(pad).grid(row=9, column=0, sticky="ew", pady=10)

        self.status = tk.Text(
            pad,
            height=10,
            wrap="word",
            state="disabled",
        )
        self.status.grid(row=10, column=0, sticky="nsew")

        bottom = ttk.Frame(pad)
        bottom.grid(row=11, column=0, sticky="ew", pady=(10, 0))
        bottom.grid_columnconfigure(0, weight=1)

        self.clear_cache_btn = ttk.Button(
            bottom,
            text="清除敏感缓存",
            command=self.clear_sensitive_cache_ui,
        )
        self.clear_cache_btn.grid(
            row=0, column=1, sticky="e", padx=(0, 8)
        )

        self.existing_preview_btn = ttk.Button(
            bottom,
            text="预览已有聊天",
            command=self.open_existing_preview,
        )
        self.existing_preview_btn.grid(
            row=0, column=2, sticky="e", padx=(0, 8)
        )
        self.preview_btn = ttk.Button(
            bottom,
            text="打开聊天预览",
            command=self.open_preview,
            state="disabled",
        )
        self.preview_btn.grid(row=0, column=3, sticky="e", padx=(0, 8))

        self.open_btn = ttk.Button(
            bottom,
            text="打开导出文件夹",
            command=self.open_output,
            state="disabled",
        )
        self.open_btn.grid(row=0, column=4, sticky="e")

        # 启动时只自动清理本项目自己的失效残留。
        # 不自动碰旧版共享的 %TEMP%\wechatauto_db。
        startup_cache_report = clear_current_sensitive_cache()
        removed = startup_cache_report.get("removed") or []
        failed = startup_cache_report.get("failed") or []
        if removed:
            self.log(
                f"已自动清理上次异常退出留下的敏感临时缓存：{len(removed)} 个目录。"
            )
        if failed:
            self.log(
                "检测到敏感临时缓存残留，但自动清理失败。"
                "可在确认没有导出任务运行后使用‘清除敏感缓存’重试。"
            )

        self.entry.focus_set()
        self.after(100, self.poll_queue)

    def on_transcribe_toggle(self):
        if self.transcribe_var.get():
            self.voices_var.set(True)

    def clear_sensitive_cache_ui(self):
        confirmed = messagebox.askyesno(
            APP_TITLE,
            "将清除本工具可能留下的敏感临时缓存，包括：\n\n"
            "1. v1.3.4 当前版本的一次性临时工作目录；\n"
            "2. v1.3.3 及更早版本 / wechatauto-replica 默认保存在 "
            "%TEMP%\\wechatauto_db 下的数据库密钥、图片密钥和解密数据库缓存。\n\n"
            "这不会删除微信原始聊天数据库，也不会删除已经导出的聊天结果。\n\n"
            "如果还有其他程序正在使用 wechatauto-replica，请先关闭它们。\n\n"
            "确定继续吗？",
        )
        if not confirmed:
            return

        self._set_export_buttons("disabled")
        self.clear_cache_btn.configure(state="disabled")
        self.log("")
        self.log("正在清除敏感临时缓存…")
        threading.Thread(
            target=self.clear_sensitive_cache_worker,
            daemon=True,
        ).start()

    def clear_sensitive_cache_worker(self):
        try:
            report = clear_sensitive_cache()
            self.q.put(("cache_cleared", report))
        except Exception as exc:
            self.q.put((
                "cache_clear_error",
                f"{type(exc).__name__}: {exc}",
            ))

    def choose_db_dir(self):
        self.log("正在查找本机微信数据目录……")
        try:
            path = choose_wechat_data_dir(
                self,
                current=self.db_dir_var.get().strip() or None,
            )
        except Exception as exc:
            self.log(f"查找微信数据目录失败：{type(exc).__name__}: {exc}")
            path = filedialog.askdirectory(
                parent=self,
                initialdir=self.db_dir_var.get() or str(Path.home()),
            )
        if path:
            self.db_dir_var.set(path)
            self.log(f"已选择微信数据目录：{path}")

    def choose_out(self):
        path = filedialog.askdirectory(
            initialdir=self.out_var.get() or str(app_dir())
        )
        if path:
            self.out_var.set(path)

    def log(self, msg):
        self.status.configure(state="normal")
        self.status.insert("end", str(msg) + "\n")
        self.status.see("end")
        self.status.configure(state="disabled")

    def _set_export_buttons(self, state):
        self.export_btn.configure(state=state)
        self.export_all_btn.configure(state=state)
        self.scan_btn.configure(state=state)

    def _warn_wechat_not_running(self):
        self.log("未检测到正在运行的 Windows 微信。")
        messagebox.showwarning(
            APP_TITLE,
            "未检测到正在运行的 Windows 微信。\n\n"
            "请先启动并登录微信，保持微信在后台运行，然后重新开始导出。",
        )

    def _check_media_ready(self, transcribe_voices):
        if self.voices_var.get():
            ok, reason = rust_silk_status()
            if not ok:
                install_now = messagebox.askyesno(
                    APP_TITLE,
                    "当前没有找到 rust-silk 语音解码器。\n\n"
                    "微信语音需要它才能从 SILK 转成 WAV；"
                    "本地语音转文字也需要先得到 WAV。\n\n"
                    "程序会从 rust-silk 官方 GitHub Release 下载固定的 v0.1.3，"
                    "并在安装前校验 SHA-256。\n\n"
                    "现在下载并安装吗？",
                )
                if install_now:
                    self._set_export_buttons("disabled")
                    self.log("")
                    self.log("开始安装 rust-silk 语音解码器…")
                    threading.Thread(
                        target=self.install_rust_silk_worker,
                        daemon=True,
                    ).start()
                    return False
                if transcribe_voices:
                    messagebox.showwarning(
                        APP_TITLE,
                        "未安装 rust-silk，无法把 SILK 转成 WAV，"
                        "因此不能继续本地语音转文字。",
                    )
                    return False

        if transcribe_voices:
            ok, reason = local_asr_status()
            if not ok:
                if reason.startswith("本地语音识别运行库不可用"):
                    messagebox.showerror(
                        APP_TITLE,
                        "当前程序缺少本地语音识别运行库。\n\n"
                        "如果你使用的是 GitHub 发布的 Windows 版，请重新下载最新构建；"
                        "如果从源码运行，请先安装 requirements.txt。\n\n"
                        f"详细信息：{reason}",
                    )
                    return False

                install_now = messagebox.askyesno(
                    APP_TITLE,
                    "本地语音识别模型还没有安装。\n\n"
                    "需要从 sherpa-onnx 官方 GitHub Release 下载约 230 MB 的 "
                    "SenseVoice Small Int8 模型。\n"
                    "模型只下载一次，之后识别在本机完成，不上传聊天语音。\n\n"
                    "现在下载并安装吗？",
                )
                if install_now:
                    self._set_export_buttons("disabled")
                    self.log("")
                    self.log("开始安装本地语音识别模型…")
                    threading.Thread(
                        target=self.install_asr_worker,
                        daemon=True,
                    ).start()
                return False
        return True

    def _begin_export(self):
        self._set_export_buttons("disabled")
        self.clear_cache_btn.configure(state="disabled")
        self.open_btn.configure(state="disabled")
        self.preview_btn.configure(state="disabled")
        self.last_output = None
        self.last_result = None
        self.log("")

    def _window_args(self) -> dict:
        """把“最近 N 天”转成 since/until；留空表示不限时间。

        单会话与批量两个入口共用，非法值统一转成可弹窗的 ValueError。
        """
        raw = self.last_days_var.get().strip()
        if not raw:
            return {"since": None, "until": None}
        # 结束时间故意留空：导出过程中新到的消息也算进来，避免卡边界丢消息。
        return last_days_window(raw)

    def _window_desc(self) -> str:
        """确认框与日志里展示的时间范围文案。"""
        raw = self.last_days_var.get().strip()
        return f"最近 {raw} 天" if raw else "不限时间"

    def start_export(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning(APP_TITLE, "请输入好友备注名、昵称或群名。")
            return

        if not is_wechat_running():
            self._warn_wechat_not_running()
            return

        transcribe_voices = self.transcribe_var.get()
        if transcribe_voices:
            self.voices_var.set(True)

        try:
            window = self._window_args()
        except ValueError as exc:
            messagebox.showwarning(APP_TITLE, str(exc))
            return

        self.pending_mode = "single"
        self.pending_usernames = None
        if not self._check_media_ready(transcribe_voices):
            return

        self._begin_export()
        self.log(f"开始导出：{name}（时间范围：{self._window_desc()}）")

        thread = threading.Thread(
            target=self.worker,
            args=(
                name,
                self.out_var.get().strip() or str(app_dir() / "exports"),
                self.images_var.get(),
                self.files_var.get(),
                self.voices_var.get(),
                self.videos_var.get(),
                transcribe_voices,
                self.db_dir_var.get().strip() or None,
                window,
            ),
            daemon=True,
        )
        thread.start()

    def start_export_all(self, only_usernames=None):
        # 先校验时间输入（非法值在弹确认框之前就该拦下），再查微信进程。
        try:
            window = self._window_args()
        except ValueError as exc:
            messagebox.showwarning(APP_TITLE, str(exc))
            return
        window_desc = self._window_desc()

        if not is_wechat_running():
            self._warn_wechat_not_running()
            return

        if only_usernames is None:
            if not messagebox.askyesno(
                APP_TITLE,
                "将导出本机所有能够从本地消息表可靠识别的私聊和群聊。\n\n"
                "· 只处理实际存在本地消息表的会话，不把‘只加过好友’当成聊天；\n"
                "· 无法可靠反查 username 的消息表会跳过，不会猜测身份；\n"
                "· 每个会话使用由稳定 username 派生的固定目录，避免同名联系人串目录；\n"
                "· 勾选图片、文件、语音或视频时可能占用大量磁盘空间；\n"
                "· 如需先小范围试跑，可用命令行 --all --limit 20。\n\n"
                f"时间范围：{window_desc}。\n\n"
                "确定开始吗？",
            ):
                return
        else:
            if not messagebox.askyesno(
                APP_TITLE,
                f"将导出已选 {len(only_usernames)} 个会话。\n\n"
                "· 只导出刚才在“选择要导出的会话”里选中的会话；\n"
                "· 勾选图片、文件、语音或视频时可能占用大量磁盘空间；\n\n"
                f"时间范围：{window_desc}。\n\n"
                "确定开始吗？",
            ):
                return

        transcribe_voices = self.transcribe_var.get()
        if transcribe_voices:
            self.voices_var.set(True)

        if only_usernames is None:
            self.pending_mode = "all"
            self.pending_usernames = None
        else:
            self.pending_mode = "selected"
            self.pending_usernames = tuple(only_usernames)
        if not self._check_media_ready(transcribe_voices):
            return

        self._begin_export()
        if only_usernames is None:
            self.log(f"开始导出全部聊天…（时间范围：{window_desc}）")
        else:
            self.log(
                f"开始导出已选 {len(only_usernames)} 个会话…"
                f"（时间范围：{window_desc}）"
            )
        thread = threading.Thread(
            target=self.worker_all,
            args=(
                self.out_var.get().strip() or str(app_dir() / "exports"),
                self.images_var.get(),
                self.files_var.get(),
                self.voices_var.get(),
                self.videos_var.get(),
                transcribe_voices,
                self.db_dir_var.get().strip() or None,
                window,
                tuple(only_usernames) if only_usernames is not None else None,
            ),
            daemon=True,
        )
        thread.start()

    def start_scan_pick(self):
        """「扫描选择…」入口：缓存命中直接弹出对话框，否则后台扫描会话。"""
        if not is_wechat_running():
            self._warn_wechat_not_running()
            return
        db_dir_raw = self.db_dir_var.get()
        cache = self._scan_cache
        if cache is not None and cache[0] == db_dir_raw:
            self._open_chat_picker(cache[1])
            return
        self._scan_chats_async()

    def _scan_chats_async(self, target=None):
        """后台扫描本地会话。target=None 表示扫描完成后新开选择对话框；
        传入已打开的对话框则表示其中的「重新扫描」，完成后刷新该对话框。"""
        db_dir_raw = self.db_dir_var.get()
        self._set_export_buttons("disabled")
        self.log("")
        self.log("正在扫描本地会话…")
        threading.Thread(
            target=self.scan_worker,
            args=(db_dir_raw, target),
            daemon=True,
        ).start()

    def scan_worker(self, db_dir_raw, target=None):
        # 工作线程内绝不直接碰 Tkinter，结果经队列回主线程处理。
        try:
            chats = list_chats(
                db_dir=db_dir_raw.strip() or None,
                progress=lambda m: self.q.put(("log", m)),
            )
            self.q.put(("scan_done", (db_dir_raw, chats, target)))
        except Exception as exc:
            self.q.put(("scan_error", (f"{type(exc).__name__}: {exc}", target)))

    def _open_chat_picker(self, chats):
        ChatPickerDialog(self, chats, on_confirm=self._on_chats_picked)

    def _on_chats_picked(self, chats, usernames):
        names = []
        for chat in chats:
            if chat.get("username") in usernames:
                names.append(str(chat.get("name") or "").strip())
        shown = "、".join(names[:5])
        if len(names) > 5:
            shown += "等"
        self.log(f"已选择 {len(usernames)} 个会话：{shown}")
        self.start_export_all(usernames)

    def install_asr_worker(self):
        try:
            install_local_asr_model(
                progress=lambda m: self.q.put(("log", m))
            )
            self.q.put(("asr_installed", None))
        except Exception as exc:
            self.q.put(("asr_error", f"{type(exc).__name__}: {exc}"))

    def install_rust_silk_worker(self):
        try:
            install_rust_silk(
                progress=lambda m: self.q.put(("log", m))
            )
            self.q.put(("rust_silk_installed", None))
        except Exception as exc:
            self.q.put(("rust_silk_error", f"{type(exc).__name__}: {exc}"))

    def worker(
        self,
        name,
        outdir,
        export_images,
        export_files,
        export_voices,
        export_videos,
        transcribe_voices,
        db_dir,
        window=None,
    ):
        try:
            result = export_chat(
                name,
                outdir,
                progress=lambda m: self.q.put(("log", m)),
                export_images=export_images,
                export_files=export_files,
                export_voices=export_voices,
                export_videos=export_videos,
                transcribe_voices=transcribe_voices,
                db_dir=db_dir,
                **(window or {}),
            )
            self.q.put(("done", result))
        except Exception as e:
            self.q.put(("error", f"{type(e).__name__}: {e}"))

    def worker_all(
        self,
        outdir,
        export_images,
        export_files,
        export_voices,
        export_videos,
        transcribe_voices,
        db_dir,
        window=None,
        only_usernames=None,
    ):
        try:
            result = export_all_chats(
                outdir,
                progress=lambda m: self.q.put(("log", m)),
                export_images=export_images,
                export_files=export_files,
                export_voices=export_voices,
                export_videos=export_videos,
                transcribe_voices=transcribe_voices,
                db_dir=db_dir,
                only_usernames=only_usernames,
                **(window or {}),
            )
            self.q.put(("all_done", result))
        except Exception as exc:
            self.q.put(("error", f"{type(exc).__name__}: {exc}"))

    def poll_queue(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self.log(payload)
                elif kind == "done":
                    self.last_output = payload["output_dir"]
                    self.last_result = payload
                    self.log(f"输出：{payload['output_dir']}")
                    self._set_export_buttons("normal")
                    self.clear_cache_btn.configure(state="normal")
                    self.open_btn.configure(state="normal")
                    self.preview_btn.configure(state="normal")

                    stats = payload.get("media_stats") or {}
                    media_line = (
                        f"\n图片：{stats.get('images_exported', 0)}/"
                        f"{stats.get('images_requested', 0)}"
                        f"\n文件：{stats.get('files_exported', 0)}/"
                        f"{stats.get('files_requested', 0)}"
                        f"\n语音：{stats.get('voices_exported', 0)}/"
                        f"{stats.get('voices_requested', 0)}"
                        f"（WAV {stats.get('voices_decoded', 0)}）"
                        f"\n语音转文字：{stats.get('voice_transcripts', 0)}/"
                        f"{stats.get('voices_requested', 0)}"
                        f"（本地 {stats.get('voice_transcripts_local', 0)}，"
                        f"缓存 {stats.get('voice_transcripts_cached', 0)}）"
                        f"\n视频：{stats.get('videos_exported', 0)}/"
                        f"{stats.get('videos_requested', 0)}"
                    )

                    cleanup_ok = payload.get("sensitive_cache_cleanup", True)
                    cleanup_error = payload.get("sensitive_cache_cleanup_error")
                    cleanup_note = (
                        ""
                        if cleanup_ok
                        else (
                            "\n\n⚠ 敏感临时缓存自动清理失败。"
                            "\n请点击“清除敏感缓存”重试。"
                            + (f"\n详细信息：{cleanup_error}" if cleanup_error else "")
                        )
                    )
                    show_result = (
                        messagebox.showinfo
                        if cleanup_ok
                        else messagebox.showwarning
                    )
                    show_result(
                        APP_TITLE,
                        f"导出完成。\n\n"
                        f"类型：{'群聊' if payload['is_group'] else '私聊'}\n"
                        f"消息数：{payload['message_count']}\n"
                        f"会话：{payload['chat_name']}"
                        f"{media_line}\n\n"
                        "已生成 TXT、Markdown 和 JSON。"
                        f"{cleanup_note}",
                    )
                elif kind == "all_done":
                    self.last_output = payload["output_dir"]
                    self.last_result = None
                    self.log(f"输出：{payload['output_dir']}")
                    self._set_export_buttons("normal")
                    self.clear_cache_btn.configure(state="normal")
                    self.open_btn.configure(state="normal")
                    self.preview_btn.configure(state="disabled")

                    cleanup_ok = payload.get("sensitive_cache_cleanup", True)
                    cleanup_error = payload.get("sensitive_cache_cleanup_error")
                    cleanup_note = (
                        ""
                        if cleanup_ok
                        else (
                            "\n\n⚠ 敏感临时缓存自动清理失败。"
                            "\n请点击‘清除敏感缓存’重试。"
                            + (f"\n详细信息：{cleanup_error}" if cleanup_error else "")
                        )
                    )
                    unresolved = payload.get("unresolved_message_tables", 0)
                    unresolved_note = (
                        f"\n无法可靠反查身份、已跳过的消息表：{unresolved}"
                        if unresolved
                        else ""
                    )
                    show_result = (
                        messagebox.showinfo
                        if cleanup_ok
                        else messagebox.showwarning
                    )
                    done_title = (
                        "已选会话导出完成"
                        if self.pending_mode == "selected"
                        else "全部聊天导出完成"
                    )
                    show_result(
                        APP_TITLE,
                        f"{done_title}。\n\n"
                        f"可可靠识别会话：{payload['discovered_total']}\n"
                        f"本次处理：{payload['selected_total']}\n"
                        f"成功：{payload['exported']}\n"
                        f"无消息：{payload['skipped_empty']}\n"
                        f"失败：{payload['failed']}\n"
                        f"消息总数：{payload['total_messages']}"
                        f"{unresolved_note}\n\n"
                        f"总索引：\n{payload['index_md']}"
                        f"{cleanup_note}",
                    )
                elif kind == "cache_cleared":
                    self._set_export_buttons("normal")
                    self.clear_cache_btn.configure(state="normal")
                    removed = payload.get("removed") or []
                    failed = payload.get("failed") or []
                    if removed:
                        for path in removed:
                            self.log(f"已清除：{path}")
                    else:
                        self.log("没有发现需要清理的敏感缓存。")
                    if failed:
                        details = "\n".join(
                            f"{item.get('path')}：{item.get('error')}"
                            for item in failed
                        )
                        self.log("部分敏感缓存清理失败。")
                        messagebox.showwarning(
                            APP_TITLE,
                            "部分敏感缓存清理失败。\n\n"
                            "请确认没有其他程序正在使用这些文件，然后重试。\n\n"
                            + details,
                        )
                    else:
                        messagebox.showinfo(
                            APP_TITLE,
                            "敏感缓存清理完成。"
                            if removed
                            else "没有发现需要清理的敏感缓存。",
                        )
                elif kind == "cache_clear_error":
                    self._set_export_buttons("normal")
                    self.clear_cache_btn.configure(state="normal")
                    self.log("敏感缓存清理失败：" + payload)
                    messagebox.showerror(
                        APP_TITLE,
                        "敏感缓存清理失败：\n\n" + payload,
                    )
                elif kind == "asr_installed":
                    self._set_export_buttons("normal")
                    self.log("本地语音识别模型安装完成。")
                    messagebox.showinfo(
                        APP_TITLE,
                        "本地语音识别模型安装完成。\n\n"
                        "现在可以重新开始导出。",
                    )
                elif kind == "rust_silk_installed":
                    self._set_export_buttons("normal")
                    self.log("rust-silk 安装完成，继续导出。")
                    # 按 pending_mode 恢复对应导出入口；selected 模式带参恢复，
                    # 避免把子集导出放大成全量。
                    if self.pending_mode == "single":
                        self.after(0, self.start_export)
                    elif self.pending_mode == "all":
                        self.after(0, self.start_export_all)
                    else:
                        self.after(0, self.start_export_all, self.pending_usernames)
                elif kind == "rust_silk_error":
                    self._set_export_buttons("normal")
                    self.log("rust-silk 安装失败：" + payload)
                    messagebox.showerror(
                        APP_TITLE,
                        "rust-silk 安装失败：\n\n" + payload,
                    )
                elif kind == "asr_error":
                    self._set_export_buttons("normal")
                    self.log("本地语音识别模型安装失败：" + payload)
                    messagebox.showerror(
                        APP_TITLE,
                        "本地语音识别模型安装失败：\n\n" + payload,
                    )
                elif kind == "error":
                    self._set_export_buttons("normal")
                    self.clear_cache_btn.configure(state="normal")
                    self.log("导出失败：" + payload)
                    messagebox.showerror(
                        APP_TITLE,
                        "导出失败：\n\n" + payload,
                    )
                elif kind == "scan_done":
                    db_dir_raw, chats, target = payload
                    self._scan_cache = (db_dir_raw, chats)
                    self._set_export_buttons("normal")
                    if target is None:
                        self._open_chat_picker(chats)
                    elif target.winfo_exists():
                        # 对话框内「重新扫描」完成：刷新列表并恢复其控件。
                        target.refresh_chats(chats)
                elif kind == "scan_error":
                    error_text, target = payload
                    self._set_export_buttons("normal")
                    self.log("扫描本地会话失败：" + error_text)
                    messagebox.showerror(
                        APP_TITLE,
                        "扫描本地会话失败：\n\n" + error_text,
                    )
                    if target is not None and target.winfo_exists():
                        target.on_scan_error()
        except queue.Empty:
            pass

        self.after(100, self.poll_queue)

    def open_preview(self):
        if not self.last_result:
            return
        json_path = self.last_result.get("json")
        if json_path and Path(json_path).is_file():
            open_chat_preview(self, json_path)

    def open_existing_preview(self):
        initial_dir = Path(
            self.out_var.get().strip() or str(app_dir() / "exports")
        )
        if not initial_dir.is_dir():
            initial_dir = app_dir()

        folder = filedialog.askdirectory(
            parent=self,
            title="选择已导出的聊天文件夹",
            initialdir=str(initial_dir),
        )
        if not folder:
            return

        json_path = Path(folder) / "chat_full_parsed.json"
        if not json_path.is_file():
            messagebox.showwarning(
                APP_TITLE,
                "这个文件夹里没有找到 chat_full_parsed.json。\n\n"
                "请选择一个具体的聊天导出文件夹。",
            )
            return

        open_chat_preview(self, json_path)

    def open_output(self):
        if not self.last_output:
            return
        path = Path(self.last_output)
        if path.exists():
            os.startfile(str(path))


if __name__ == "__main__":
    App().mainloop()
