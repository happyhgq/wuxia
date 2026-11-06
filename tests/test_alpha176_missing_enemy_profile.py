"""Alpha176：缺少敌人战斗配置时应安全退出，不运行世界压力计算。"""
from unittest.mock import patch
import combat
from player import Player


def test_missing_enemy_profile_exits_before_world_pressure_or_input():
    player = Player("缺失配置测试", "散人")
    player.location = "test_room"
    with patch("combat.get_enemy_profile", return_value={}), \
         patch("combat.apply_world_combat_pressure") as pressure, \
         patch("builtins.input", side_effect=AssertionError("不应进入战斗输入")):
        combat.combat(player, "不存在的敌人")
    pressure.assert_not_called()
