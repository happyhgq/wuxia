"""Alpha317：人物标签不重复拼接称号。"""
import actor_display
import engine


def test_room_label_never_repeats_rank_title():
    for npc_name, info in engine.NPCS.items():
        label = actor_display.format_room_label(npc_name)
        rank = str((info or {}).get("rank_title", "")).strip()
        if rank:
            assert not label.startswith(rank + rank), (npc_name, label)


def test_known_duplicate_labels_render_once():
    expected = {
        "捕头": "归云城捕头",
        "狱卒": "府衙狱卒",
        "说书先生": "听风说书先生",
        "巡河老兵": "北境巡河老兵",
    }
    for npc_name, label in expected.items():
        assert actor_display.format_room_label(npc_name) == label
