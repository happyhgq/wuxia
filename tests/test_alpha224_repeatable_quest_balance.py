import contextlib
import io
import json
from pathlib import Path

import engine
from actions import handle_quest
from player import Player


def test_repeatable_sect_contract_has_cooldown_and_non_farmable_permanent_rewards():
    quest = engine.QUESTS["铁衣门历练·护路除匪"]
    assert quest["repeatable"] is True
    assert quest["repeat_cooldown_ticks"] == 48
    assert quest["repeat_reward"] == {"exp": 40, "gold": 22}
    assert "sect_reputation" not in quest["repeat_reward"]
    assert "honor_delta" not in quest["repeat_reward"]


def test_repeatable_quest_cannot_be_reaccepted_during_cooldown():
    p = Player("历练冷却测试", "铁衣门")
    p.completed_quests.append("铁衣门历练·护路除匪")
    p.set_var("quest_clock", 50)
    p.set_var("quest_repeat_last_completed:铁衣门历练·护路除匪", 40)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        handle_quest(p, "jiequ", ["铁衣门历练·护路除匪"])
    assert "还需等待" not in output.getvalue()
    assert "再等待 38 个世界时刻" in output.getvalue()
    assert "铁衣门历练·护路除匪" not in p.active_quests


def test_repeatable_quest_can_be_reaccepted_after_cooldown():
    p = Player("历练冷却结束测试", "铁衣门")
    p.location = "tieyi_guest_hall"
    p.completed_quests.append("铁衣门历练·护路除匪")
    p.set_var("quest_clock", 90)
    p.set_var("quest_repeat_last_completed:铁衣门历练·护路除匪", 40)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        handle_quest(p, "jiequ", ["铁衣门历练·护路除匪"])
    assert "已接取任务" in output.getvalue()
    assert "铁衣门历练·护路除匪" in p.active_quests


def test_repeatable_quest_npc_status_matches_cooldown_gate():
    from actions import _quest_npc_status

    p = Player("历练状态一致性测试", "铁衣门")
    p.completed_quests.append("铁衣门历练·护路除匪")
    p.set_var("quest_clock", 50)
    p.set_var("quest_repeat_last_completed:铁衣门历练·护路除匪", 40)
    state, detail = _quest_npc_status(p, "铁衣门历练·护路除匪")
    assert state == "未开放"
    assert "38 个世界时刻" in detail

    p.set_var("quest_clock", 90)
    state, detail = _quest_npc_status(p, "铁衣门历练·护路除匪")
    assert state == "未领取"


def test_only_intended_repeatable_quest_uses_repeat_reward_policy():
    data = json.loads((Path(__file__).parents[1] / "data" / "quests.json").read_text(encoding="utf-8"))
    repeatable = [name for name, quest in data.items() if quest.get("repeatable")]
    assert repeatable == [
        "铁衣门历练·护路除匪",
        "断魂岭·巡道除匪",
        "少林·伏魔护寺",
        "武当·夜巡断魂",
        "华山·绝壁试锋",
        "铁衣门·断魂护镖",
        "断魂岭·精铁换药",
        "断魂岭·皮货换药",
        "断魂岭·断锋回炉",
        "沉河·堰口除傀",
        "百草堂·草药换伤药",
        "悦来客栈·野味换干粮",
        "打铁铺·军械回炉",
        "沉河·铜钱换伤药",
    ]
    for name in repeatable:
        repeat = data[name]["repeat_reward"]
        assert "sect_reputation" not in repeat, name
        assert "honor_delta" not in repeat, name
        assert data[name]["repeat_cooldown_ticks"] > 0, name
