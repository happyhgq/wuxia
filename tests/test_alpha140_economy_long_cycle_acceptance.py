"""Alpha140：锁定经济资金守恒、分批推进与存档续跑的一致性。"""
from economy import EconomyManager


def test_long_cycle_tracked_gold_is_conserved_except_recorded_caravan_upkeep():
    manager = EconomyManager()
    manager.update(10_000)
    audit = manager.economic_audit_snapshot()

    # 默认经济池：城镇本金 + 一次性 NPC 钱包 + 一次性商队本金。
    initial_pool = 5_000 + audit["seeded_npc_gold"] + audit["seeded_caravan_gold"]
    assert audit["tick"] == 10_000
    assert audit["seeded_npc_gold"] == 8_000
    assert audit["seeded_caravan_gold"] == 5_450
    # NPC/商队之间的买卖只是转移资金；唯一允许的净减少是已记账的商队维护费。
    assert audit["tracked_gold"] + audit["destroyed_caravan_upkeep"] == initial_pool


def test_economy_tick_batching_does_not_change_results():
    one_shot = EconomyManager()
    one_shot.update(1_200)

    batched = EconomyManager()
    for _ in range(12):
        batched.update(100)

    assert batched.export_state() == one_shot.export_state()


def test_save_resume_matches_uninterrupted_economy_simulation():
    uninterrupted = EconomyManager()
    uninterrupted.update(1_200)

    first_half = EconomyManager()
    first_half.update(600)
    resumed = EconomyManager(first_half.export_state())
    resumed.update(600)

    assert resumed.export_state() == uninterrupted.export_state()
