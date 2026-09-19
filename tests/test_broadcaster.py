"""播报策略测试（rules/02 文案模板：礼物数量、金额阈值、开关过滤）。"""
from config.preferences import Preferences
from core.broadcaster import Broadcaster
from platforms.base import LiveEvent


def make_broadcaster(**prefs_kwargs) -> Broadcaster:
    return Broadcaster(Preferences(**prefs_kwargs), queue=None)


def test_gift_raw_text_includes_count():
    """礼物模板播报带数量：xxx投喂了 n 个礼物名。"""
    b = make_broadcaster(broadcast_gift=True)
    e = LiveEvent(type="gift", user_name="老板", gift_name="人气票", num=1000, amount=0.1)
    assert b.build_texts(e) == ["老板投喂了 1000 个人气票"]


def test_gift_thanks_includes_count():
    b = make_broadcaster(thanks_gift=True)
    e = LiveEvent(type="gift", user_name="老板", gift_name="人气票", num=1000, amount=0.1)
    assert b.build_texts(e) == ["感谢老板投喂的 1000 个人气票"]


def test_gift_thanks_below_threshold_no_laoban():
    """0.1 元礼物不应触发「老板大气」（金瓜子换算回归测试）。"""
    b = make_broadcaster(thanks_gift=True, amount_threshold=50.0)
    e = LiveEvent(type="gift", user_name="老板", gift_name="人气票", num=1, amount=0.1)
    assert b.build_texts(e) == ["感谢老板投喂的 1 个人气票"]


def test_gift_thanks_above_threshold_appends_laoban():
    b = make_broadcaster(thanks_gift=True, amount_threshold=50.0)
    e = LiveEvent(type="gift", user_name="老板", gift_name="火箭", num=1, amount=500.0)
    assert b.build_texts(e) == ["感谢老板投喂的 1 个火箭，老板大气"]
