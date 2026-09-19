"""B站事件归一化测试（重点：礼物金额金瓜子→元换算、数量字段）。"""
import pytest

from platforms.bilibili.events import parse_command


def test_gift_price_converts_gold_seed_to_yuan():
    """B站 price 单位是金瓜子（1元=1000金瓜子）。

    实测：0.1 元的人气票 price=100，直接当元用会显示 ¥100 并误触发老板大气。
    """
    data = {
        "cmd": "LIVE_OPEN_PLATFORM_SEND_GIFT",
        "data": {
            "uname": "老板",
            "gift_name": "人气票",
            "price": 100,
            "amount": 1,
            "gift_id": 1,
        },
    }
    (event,) = parse_command(data)
    assert event.amount == pytest.approx(0.1)  # 100金瓜子 = 0.1元


def test_gift_multiplies_by_count():
    data = {
        "cmd": "LIVE_OPEN_PLATFORM_SEND_GIFT",
        "data": {
            "uname": "老板",
            "gift_name": "小花花",
            "price": 1000,  # 1元/个
            "gift_num": 10,
        },
    }
    (event,) = parse_command(data)
    assert event.amount == pytest.approx(10.0)  # 1元 × 10个
    assert event.num == 10


def test_gift_num_defaults_to_one():
    data = {
        "cmd": "LIVE_OPEN_PLATFORM_SEND_GIFT",
        "data": {"uname": "老板", "gift_name": "小花花", "price": 1000},
    }
    (event,) = parse_command(data)
    assert event.num == 1


def test_gift_uses_official_gift_num_field():
    """官方文档：数量字段是 gift_num（我们曾误用 amount 导致数量不正确）。"""
    data = {
        "cmd": "LIVE_OPEN_PLATFORM_SEND_GIFT",
        "data": {
            "uname": "老板",
            "gift_name": "小花花",
            "price": 1000,
            "gift_num": 66,
        },
    }
    (event,) = parse_command(data)
    assert event.num == 66


def test_gift_amount_prefers_r_price():
    """官方文档：r_price 为实际价值，存在时优先于 price。"""
    data = {
        "cmd": "LIVE_OPEN_PLATFORM_SEND_GIFT",
        "data": {
            "uname": "老板",
            "gift_name": "小花花",
            "price": 2000,
            "r_price": 1000,
            "gift_num": 1,
        },
    }
    (event,) = parse_command(data)
    assert event.amount == pytest.approx(1.0)


def test_blind_gift_flag_and_amount():
    """盲盒：blind_gift.status=true → is_blind；金额用爆出价值；id 进 extra。"""
    data = {
        "cmd": "LIVE_OPEN_PLATFORM_SEND_GIFT",
        "data": {
            "uname": "老板",
            "gift_name": "干杯",
            "price": 1000,
            "gift_num": 1,
            "blind_gift": {"blind_gift_id": 10086, "status": True},
        },
    }
    (event,) = parse_command(data)
    assert event.is_blind is True
    assert event.amount == pytest.approx(1.0)
    assert event.extra["blind_gift_id"] == 10086


def test_blind_gift_no_name_mapping():
    """盲盒不做盒名映射：直接「盲盒爆出的 xx」（用户决策 2026-09-19）。"""
    data = {
        "cmd": "LIVE_OPEN_PLATFORM_SEND_GIFT",
        "data": {
            "uname": "老板",
            "gift_name": "干杯",
            "price": 1000,
            "gift_num": 1,
            "blind_gift": {"blind_gift_id": 10086, "status": True},
        },
    }
    (event,) = parse_command(data)
    assert event.is_blind is True
    assert event.gift_name == "干杯"


def test_super_chat_amount_from_rmb():
    """官方文档：醒目留言金额字段是 rmb（单位已是元），不是 price。"""
    data = {
        "cmd": "LIVE_OPEN_PLATFORM_SUPER_CHAT",
        "data": {"uname": "老板", "message": "冲！", "rmb": 30},
    }
    (event,) = parse_command(data)
    assert event.amount == 30.0
    assert event.content == "冲！"


def test_entry_cmd_matches_document():
    """官方 CMD 是 LIVE_OPEN_PLATFORM_LIVE_ROOM_ENTER（原 LIVE_ENTER_ROOM 错误）。"""
    data = {
        "cmd": "LIVE_OPEN_PLATFORM_LIVE_ROOM_ENTER",
        "data": {"uname": "路人甲"},
    }
    (event,) = parse_command(data)
    assert event.type == "entry"
    assert event.user_name == "路人甲"


def test_guard_cmd_and_nested_user_info():
    """官方 CMD 是 LIVE_OPEN_PLATFORM_GUARD（原 GUARD_BUY 错误）；
    昵称在 user_info.uname；price 为金瓜子需 /1000；数量字段 guard_num。"""
    data = {
        "cmd": "LIVE_OPEN_PLATFORM_GUARD",
        "data": {
            "user_info": {"uname": "舰长大人"},
            "guard_level": 3,
            "guard_num": 1,
            "guard_unit": "月",
            "price": 138000,
        },
    }
    (event,) = parse_command(data)
    assert event.type == "guard"
    assert event.user_name == "舰长大人"
    assert event.guard_title == "舰长"
    assert event.amount == pytest.approx(138.0)
    assert event.num == 1
