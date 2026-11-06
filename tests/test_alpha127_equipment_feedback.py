"""Alpha127：装备操作只在真实成功后报告数值变化，失败时给出可执行提示。"""
import actions


class FakePlayer:
    def __init__(self, equip_result=(True, "已装备【精铁剑】。"), unequip_result=(True, "已卸下武器。")):
        self.inventory = ["精铁剑"]
        self.equip_result = equip_result
        self.unequip_result = unequip_result
        self.save_count = 0
        self.atk = 10
        self.defense = 5

    def get_total_atk(self):
        return self.atk

    def get_total_defense(self):
        return self.defense

    def equip_item(self, name):
        if self.equip_result[0]:
            self.atk = 15
        return self.equip_result

    def unequip_item(self, slot):
        return self.unequip_result

    def save_to_file(self):
        self.save_count += 1


def test_equipment_success_reports_actual_change_without_pre_action_compare(monkeypatch, capsys):
    player = FakePlayer()
    monkeypatch.setattr(actions, "_find_inventory_item", lambda *_: "精铁剑")
    monkeypatch.setitem(actions.engine.ITEMS, "精铁剑", {"type": "weapon"})
    monkeypatch.setattr(actions, "_print_equipment_compare", lambda *_: (_ for _ in ()).throw(AssertionError("no redundant preview")))
    actions.handle_equipment_and_items(player, "equip", ["精铁剑"])
    output = capsys.readouterr().out
    assert "【装备完成】" in output
    assert "总攻击 10 → 15（+5）" in output
    assert "【装备未完成】" not in output
    assert player.save_count == 1


def test_equipment_failure_does_not_claim_stat_change_or_save(monkeypatch, capsys):
    player = FakePlayer(equip_result=(False, "当前无法装备该物品。"))
    monkeypatch.setattr(actions, "_find_inventory_item", lambda *_: "精铁剑")
    monkeypatch.setitem(actions.engine.ITEMS, "精铁剑", {"type": "weapon"})
    actions.handle_equipment_and_items(player, "equip", ["精铁剑"])
    output = capsys.readouterr().out
    assert "【装备未完成】当前无法装备该物品。" in output
    assert "接下来：确认物品类型与装备部位后重试。" in output
    assert "装备变化" not in output
    assert player.save_count == 0


def test_unequip_feedback_only_reports_success_after_mutation(capsys):
    player = FakePlayer(unequip_result=(True, "已卸下武器。"))
    actions.handle_equipment_and_items(player, "unequip", ["武器"])
    output = capsys.readouterr().out
    assert "【卸下装备完成】已卸下武器。" in output
    assert "装备栏已更新" in output
    assert player.save_count == 1
