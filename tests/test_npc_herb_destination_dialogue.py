import contextlib
import io

from actions import handle_talk_and_ask
from player import Player

RESTOCKED = ["world:main:herb_stock_replenished"]
SOLD = RESTOCKED + ["world:main:herb_sold_to_merchant"]
KEPT = RESTOCKED + ["world:main:herb_kept_for_village"]


def _talk(npc, flags, monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None, verbose=True: True)
    player = Player("药材去向台词", "散人")
    player.get_npcs_in_room = lambda location=None: [npc]
    for flag in flags:
        player.set_flag(flag, True)
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        handle_talk_and_ask(player, [npc])
    return stream.getvalue()


def _ask(npc, flags, topic, monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None, verbose=True: True)
    player = Player("药材去向追问", "散人")
    player.get_npcs_in_room = lambda location=None: [npc]
    for flag in flags:
        player.set_flag(flag, True)
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        handle_talk_and_ask(player, [npc, topic])
    return stream.getvalue()


def test_village_chief_reacts_to_merchant_ending(monkeypatch):
    output = _talk("村长", SOLD, monkeypatch)

    assert "行商的车队今早已出了村" in output
    assert "药材都留在村里了" not in output


def test_village_chief_reacts_to_village_ending(monkeypatch):
    output = _talk("村长", KEPT, monkeypatch)

    assert "药材都留在村里了" in output
    assert "行商的车队今早已出了村" not in output


def test_apothecary_reacts_to_merchant_ending(monkeypatch):
    output = _talk("药铺老板", SOLD, monkeypatch)

    assert "行商把货拉走了" in output
    assert "这批药材留在村里" not in output


def test_apothecary_reacts_to_village_ending(monkeypatch):
    output = _talk("药铺老板", KEPT, monkeypatch)

    assert "这批药材留在村里" in output
    assert "行商把货拉走了" not in output


def test_both_npcs_keep_restock_line_before_destination_is_decided(monkeypatch):
    chief = _talk("村长", RESTOCKED, monkeypatch)
    apothecary = _talk("药铺老板", RESTOCKED, monkeypatch)

    assert "百草堂的药材已经补齐" in chief
    assert "常用药材总算补齐了" in apothecary
    assert "行商" not in chief
    assert "行商" not in apothecary


def test_same_npc_line_changes_with_world_state(monkeypatch):
    for npc in ("村长", "药铺老板"):
        sold = _talk(npc, SOLD, monkeypatch)
        kept = _talk(npc, KEPT, monkeypatch)
        assert sold != kept


def test_apothecary_topic_ask_explains_offer_before_choice(monkeypatch):
    output = _ask("药铺老板", RESTOCKED + ["quest_active:百草堂·药材去向"], "药材去向", monkeypatch)

    assert "归云城行商开的价不低" in output
    assert "并不知道什么信息" not in output


def test_apothecary_topic_ask_uses_ending_line_after_choice(monkeypatch):
    sold = _ask("药铺老板", SOLD, "药材去向", monkeypatch)
    kept = _ask("药铺老板", KEPT, "药材去向", monkeypatch)

    assert "行商把货拉走了" in sold
    assert "并不知道什么信息" not in sold
    assert "这批药材留在村里" in kept
    assert "并不知道什么信息" not in kept


def test_unknown_topic_still_unknown_without_conditional_dialogue(monkeypatch):
    output = _ask("菜贩孙婶", [], "很冷僻的话题", monkeypatch)

    assert "并不知道什么信息" in output
