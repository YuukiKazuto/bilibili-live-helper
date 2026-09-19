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
            "amount": 10,
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
