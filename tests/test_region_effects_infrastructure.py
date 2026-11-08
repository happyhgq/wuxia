import engine
import region_activity
from data_validator import check_region_effects

ZONES = {"main", "bandit_zone"}


class _WorldHolder:
    def __init__(self, world_state):
        self.world_state = world_state


def _world():
    return {"flags": {}, "variables": {}}


def test_region_effects_write_permanent_region_delta():
    world = _world()

    engine.apply_world_effects(
        world, {"region_effects": {"main": {"commerce": 12, "travel": 4}}}
    )

    assert region_activity.get_permanent_region_delta(_WorldHolder(world), "main") == {
        "security": 0,
        "commerce": 12,
        "travel": 4,
    }
    row = world["variables"]["region_activity"]["main"]
    assert row["events"] == {}


def test_region_effects_accumulate_on_existing_activity():
    world = {
        "flags": {},
        "variables": {
            "region_activity": {
                "main": {
                    "security": -5,
                    "commerce": 3,
                    "travel": 0,
                    "events": {"恶人:山贼": {"last_reward_clock": 7}},
                }
            }
        },
    }

    engine.apply_world_effects(
        world, {"region_effects": {"main": {"security": 8, "commerce": -4}}}
    )

    row = world["variables"]["region_activity"]["main"]
    assert row["security"] == 3
    assert row["commerce"] == -1
    assert row["travel"] == 0
    assert row["events"] == {"恶人:山贼": {"last_reward_clock": 7}}


def test_region_effects_clamp_to_persistent_limits():
    world = _world()

    engine.apply_world_effects(
        world, {"region_effects": {"main": {"commerce": 99, "security": -99}}}
    )

    delta = region_activity.get_permanent_region_delta(_WorldHolder(world), "main")
    assert delta["commerce"] == 30
    assert delta["security"] == -60


def test_region_effects_ignore_malformed_entries():
    world = _world()

    engine.apply_world_effects(
        world,
        {
            "region_effects": {
                "": {"security": 5},
                "main": "不是对象",
                "bandit_zone": {"security": True, "commerce": "3", "travel": 2, "honor": 5},
            }
        },
    )

    state = world["variables"]["region_activity"]
    assert "" not in state
    assert "main" not in state
    row = state["bandit_zone"]
    assert row["security"] == 0
    assert row["commerce"] == 0
    assert row["travel"] == 2
    assert "honor" not in row


def test_region_effects_reject_non_object_without_partial_write():
    world = _world()

    engine.apply_world_effects(
        world, {"set_flags": {"world:test": True}, "region_effects": ["main"]}
    )

    assert world == {"flags": {}, "variables": {}}


def test_validator_accepts_valid_region_effects():
    errors = []

    check_region_effects(
        {"region_effects": {"main": {"security": -5, "commerce": 12}}},
        "任务 测试",
        ZONES,
        errors,
    )

    assert errors == []


def test_validator_rejects_bad_region_effects():
    errors = []

    check_region_effects(
        {
            "region_effects": {
                "nowhere": {"security": 5},
                "main": {"honor": 1, "commerce": True, "travel": 99},
            }
        },
        "任务 测试",
        ZONES,
        errors,
    )

    joined = "\n".join(errors)
    assert "region_effects 引用不存在的区域 nowhere" in joined
    assert "region_effects.main 不支持字段 honor" in joined
    assert "region_effects.main.commerce 必须为整数" in joined
    assert "region_effects.main.travel 超出 -60~30" in joined


def test_validator_ignores_effects_without_region_effects():
    errors = []

    check_region_effects({"relations": {"村长": 3}}, "任务 测试", ZONES, errors)
    check_region_effects({"region_effects": "坏数据"}, "任务 测试", ZONES, errors)

    assert errors == ["任务 测试: region_effects 必须为对象"]
