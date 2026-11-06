"""Alpha191：门派与世界势力审计的结构性基线检查。"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def test_existing_sects_have_maps_skills_and_quest_content():
    sects = load("sects.json")
    skills = load("skills.json")
    rooms = load("rooms.json")
    quests = load("quests.json")
    expected = {
        "少林": ("shaolin_mountain", "少林历练·黑风除恶"),
        "武当": ("wudang_mountain", "武当历练·以静制动"),
        "华山": ("huashan_mountain", "华山历练·磨剑黑风"),
    }
    zones = {room.get("zone", "main") for room in rooms.values()}
    for sect, (zone, quest) in expected.items():
        assert sect in sects
        assert sect in skills and skills[sect]
        assert zone in zones
        assert quest in quests
        assert sects[sect].get("exclusive_skills")


def test_formal_sects_are_integrated_with_world_factions():
    sects = load("sects.json")
    factions = load("factions.json")
    regions = load("world_regions.json")
    npcs = load("npcs.json")
    expected = {"少林": "shaolin_mountain", "武当": "wudang_mountain", "华山": "huashan_mountain"}
    assert set(expected).issubset(sects)
    assert set(expected).issubset(factions)
    for sect, region_id in expected.items():
        assert region_id in regions
        exposure = regions[region_id].get("faction_exposure", [])
        assert "江湖" in exposure
        assert sect in exposure
        for other in expected:
            if other != sect:
                assert factions[sect]["relations"][other] == factions[other]["relations"][sect]
    # Core sect staff are registered under their own sect, while unrelated
    # affiliated figures retain their original social/official faction.
    assert npcs["少林守山僧"]["faction"] == "少林"
    assert npcs["武当守山弟子"]["faction"] == "武当"
    assert npcs["华山守门弟子"]["faction"] == "华山"
    assert npcs["捕头"]["faction"] == "官府"
