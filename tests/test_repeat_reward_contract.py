"""可重复任务复做奖励契约：只发资源，不能无限刷取永久成长。"""
import contextlib
import io
import json
import os
import shutil
import tempfile

import data_validator
import engine
from actions import handle_quest
from player import Player


QUEST = "断魂岭·精铁换药"
REPEATABLE = [name for name, info in engine.QUESTS.items()
              if isinstance(info, dict) and info.get("repeatable")]
PERMANENT_FIELDS = ("sect_reputation", "honor_delta", "infamy_delta", "jianghu_action", "jianghu_amount")


def capture(fn, *args):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = fn(*args)
    return stream.getvalue(), result


def test_current_repeatable_quests_use_resource_only_repeat_rewards():
    assert REPEATABLE
    for name in REPEATABLE:
        info = engine.QUESTS[name]
        repeat_reward = info.get("repeat_reward")
        assert isinstance(repeat_reward, dict) and repeat_reward, name
        for field in PERMANENT_FIELDS:
            assert field not in repeat_reward, name
        effects = repeat_reward.get("effects") or {}
        for field in ("increment_variables", "relations", "faction_relations"):
            assert not effects.get(field), name
        cooldown = info.get("repeat_cooldown_ticks")
        assert isinstance(cooldown, int) and not isinstance(cooldown, bool) and cooldown >= 1, name
        assert not info.get("choices"), name


def _validate_with_mutation(mutator):
    temp = tempfile.TemporaryDirectory()
    data_dir = os.path.join(temp.name, "data")
    shutil.copytree(os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"), data_dir)
    original_data_dir = data_validator.DATA_DIR
    data_validator.DATA_DIR = data_dir
    try:
        path = os.path.join(data_dir, "quests.json")
        with open(path, encoding="utf-8") as f:
            quests = json.load(f)
        mutator(quests[QUEST])
        with open(path, "w", encoding="utf-8") as f:
            json.dump(quests, f, ensure_ascii=False, indent=2)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = data_validator.main()
        return result, output.getvalue()
    finally:
        data_validator.DATA_DIR = original_data_dir
        temp.cleanup()


def test_validator_rejects_permanent_growth_in_repeat_reward():
    def mutate(info):
        info["repeat_reward"]["honor_delta"] = 5
    result, output = _validate_with_mutation(mutate)
    assert result == 1
    assert "repeat_reward 不得包含永久成长字段 honor_delta" in output


def test_validator_rejects_repeatable_without_cooldown():
    def mutate(info):
        info.pop("repeat_cooldown_ticks", None)
    result, output = _validate_with_mutation(mutate)
    assert result == 1
    assert "可重复任务必须设置正整数 repeat_cooldown_ticks" in output


def test_validator_rejects_choices_on_repeatable_quest():
    def mutate(info):
        info["choices"] = [{"id": "only", "title": "唯一结局", "reward": {"gold": 1}}]
    result, output = _validate_with_mutation(mutate)
    assert result == 1
    assert "可重复任务不支持 choices" in output


def test_missing_repeat_reward_does_not_fall_back_to_first_reward(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    info = dict(engine.QUESTS[QUEST])
    info.pop("repeat_reward", None)
    info["reward"] = {"exp": 500, "gold": 500, "honor_delta": 50, "sect_reputation": {"少林": 50}}
    monkeypatch.setitem(engine.QUESTS, QUEST, info)

    player = Player("复做回退验收", "散人")
    player.level = 15
    player.location = "duanhun_camp"
    player.completed_quests.append(QUEST)
    player.active_quests[QUEST] = 3
    player.quest_states[QUEST] = {"stage": 0, "progress": 3}
    player.inventory.extend(["断魂精铁"] * 3)

    before_honor = player._jianghu_profile().get("honor", 0)
    before_rep = player.get_sect_reputation("少林")
    before_exp, before_gold = player.exp, player.gold

    output, result = capture(handle_quest, player, "jiaofu", [QUEST])

    assert result is True
    assert "恭喜完成任务" in output
    assert player._jianghu_profile().get("honor", 0) == before_honor
    assert player.get_sect_reputation("少林") == before_rep
    assert player.exp == before_exp
    assert player.gold == before_gold
