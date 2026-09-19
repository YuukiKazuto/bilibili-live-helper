"""互动消息面板格式化测试：统一事件 → (类别标签, 展示文本)。"""
import pytest

from platforms.base import LiveEvent
from ui.event_panel import category_label, format_event


def test_danmaku_format():
    e = LiveEvent(type="danmaku", user_name="小明", content="主播666")
    label, text = format_event(e)
    assert label == "弹幕"
    assert "小明" in text
    assert "主播666" in text


def test_gift_format_includes_count_gift_and_amount():
    e = LiveEvent(type="gift", user_name="老板", gift_name="小花花", num=3, amount=1.0)
    label, text = format_event(e)
    assert label == "礼物"
    assert "老板" in text
    assert "3 个小花花" in text  # 数量展示
    assert "¥1" in text  # 金额展示


def test_super_chat_format():
    e = LiveEvent(type="super_chat", user_name="老板", content="冲！", amount=30.0)
    label, text = format_event(e)
    assert label == "醒目留言"
    assert "冲！" in text


def test_entry_follow_like_guard_formats():
    cases = [
        (LiveEvent(type="entry", user_name="甲"), "进场"),
        (LiveEvent(type="follow", user_name="乙"), "关注"),
        (LiveEvent(type="like", user_name="丙"), "点赞"),
        (LiveEvent(type="guard", user_name="丁", guard_title="舰长"), "上舰"),
    ]
    for e, expected_label in cases:
        label, text = format_event(e)
        assert label == expected_label
        assert e.user_name in text


def test_guard_format_includes_title():
    e = LiveEvent(type="guard", user_name="丁", guard_title="提督")
    _, text = format_event(e)
    assert "提督" in text


def test_unknown_type_falls_back():
    e = LiveEvent(type="mystery", user_name="某用户")
    label, text = format_event(e)
    assert label == "其他"
    assert "某用户" in text


def test_category_label_maps_all_event_types():
    """所有事件类型都有类别标签（面板需显示全部事件类型）。"""
    for t in ("danmaku", "gift", "super_chat", "entry", "follow", "guard", "like"):
        assert category_label(t) != "其他"
