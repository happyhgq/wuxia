"""Alpha253：门派晋升门槛数据驱动且兼容旧配置。"""
import copy
import json
from pathlib import Path

import engine
from player import Player

ROOT = Path(__file__).resolve().parents[1]


def test_all_real_sects_define_complete_promotion_thresholds():
    sects = json.loads((ROOT / "data" / "sects.json").read_text(encoding="utf-8"))
    expected = {
        "1": {"level": 3, "mastery": 10},
        "2": {"level": 8, "mastery": 30},
        "3": {"level": 15, "mastery": 50},
        "4": {"level": 25, "mastery": 80},
    }
    for sect in ("少林", "武当", "华山", "铁衣门"):
        assert sects[sect]["promotion_requirements"] == expected


def test_promotion_thresholds_follow_sect_data_not_hardcoded_values():
    original = copy.deepcopy(engine.SECTS["武当"])
    try:
        engine.SECTS["武当"]["promotion_requirements"] = {
            "1": {"level": 6, "mastery": 17}
        }
        player = Player("数据驱动晋升", "散人")
        player.level = 10
        assert player.join_sect("武当")[0]
        req = player.get_sect_promotion_requirements("武当")
        assert req["required_level"] == 6
        assert req["required_mastery"] == 17
    finally:
        engine.SECTS["武当"] = original


def test_missing_promotion_config_falls_back_to_legacy_thresholds():
    original = copy.deepcopy(engine.SECTS["华山"])
    try:
        engine.SECTS["华山"].pop("promotion_requirements", None)
        player = Player("旧配置兼容", "散人")
        player.level = 10
        assert player.join_sect("华山")[0]
        req = player.get_sect_promotion_requirements("华山")
        assert req["required_level"] == 3
        assert req["required_mastery"] == 10
    finally:
        engine.SECTS["华山"] = original
