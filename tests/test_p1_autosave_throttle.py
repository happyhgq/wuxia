import player as player_module
from player import Player, request_autosave


class _FakePlayer:
    def __init__(self):
        self.saves = 0

    def save_to_file(self):
        self.saves += 1
        return True


def _install_save_counter(monkeypatch):
    calls = []

    def fake_save(self, filename=None, verbose=True):
        calls.append((filename, verbose))
        return True

    monkeypatch.setattr(Player, "save_to_file", fake_save)
    return calls


def test_autosave_coalesces_within_ten_world_ticks(monkeypatch):
    calls = _install_save_counter(monkeypatch)
    player = Player("存档节流", "散人")
    player.set_var("quest_clock", 10)

    assert player.autosave() is True
    assert len(calls) == 1

    for clock in range(11, 20):
        player.set_var("quest_clock", clock)
        assert player.autosave() is True
    assert len(calls) == 1
    assert getattr(player, "_autosave_pending", False) is True
    assert player.flush_autosave() is False

    player.set_var("quest_clock", 20)
    assert player.flush_autosave() is True
    assert len(calls) == 2
    assert getattr(player, "_autosave_pending", False) is False


def test_autosave_writes_immediately_once_interval_elapsed(monkeypatch):
    calls = _install_save_counter(monkeypatch)
    player = Player("存档间隔", "散人")
    player.set_var("quest_clock", 0)
    player.autosave()

    player.set_var("quest_clock", player_module.AUTO_SAVE_INTERVAL_TICKS)
    assert player.autosave() is True
    assert len(calls) == 2


def test_force_autosave_bypasses_interval_but_keeps_safety(monkeypatch):
    calls = _install_save_counter(monkeypatch)
    player = Player("强制自动存档", "散人")
    player.set_var("quest_clock", 10)
    player.autosave()

    player.set_var("quest_clock", 11)
    assert player.autosave(force=True) is True
    assert len(calls) == 2

    player.location = "official_road"
    assert player.autosave(force=True) is True
    assert len(calls) == 2
    assert getattr(player, "_autosave_pending", False) is True


def test_explicit_save_clears_pending_autosave(tmp_path):
    player = Player("显式存档", "散人")
    target = str(tmp_path / "explicit_save.json")
    player.set_var("quest_clock", 5)
    assert player.autosave(target) is True
    player.set_var("quest_clock", 6)
    player.autosave(target)
    assert getattr(player, "_autosave_pending", False) is True

    assert player.save_to_file(target) is True
    assert getattr(player, "_autosave_pending", False) is False


def test_request_autosave_falls_back_for_fake_players():
    fake = _FakePlayer()
    assert request_autosave(fake) is True
    assert fake.saves == 1


def test_missing_safe_field_is_treated_as_dangerous(monkeypatch):
    calls = _install_save_counter(monkeypatch)
    player = Player("缺省安全字段", "散人")
    player.location = "official_road_east_2"
    player.set_var("quest_clock", 10)

    assert player._autosave_allowed() is False
    assert player.autosave() is True
    assert len(calls) == 0
    assert player.flush_autosave() is False
    assert getattr(player, "_autosave_pending", False) is True


def test_dangerous_scene_queues_until_player_returns_to_safe_room(monkeypatch):
    calls = _install_save_counter(monkeypatch)
    player = Player("危险场景挂起", "散人")
    player.location = "official_road"
    player.set_var("quest_clock", 10)

    assert player.autosave() is True
    assert len(calls) == 0
    assert player.flush_autosave() is False
    assert getattr(player, "_autosave_pending", False) is True

    player.location = "village_square"
    player.set_var("quest_clock", 20)
    assert player.flush_autosave() is True
    assert len(calls) == 1
    assert getattr(player, "_autosave_pending", False) is False


def test_in_combat_queues_and_flushes_after_combat(monkeypatch):
    calls = _install_save_counter(monkeypatch)
    player = Player("战斗中存档", "散人")
    player.location = "village_square"
    player.set_var("quest_clock", 10)
    player._in_combat = True

    assert player._autosave_allowed() is False
    assert player.autosave() is True
    assert len(calls) == 0
    assert player.flush_autosave() is False

    player._in_combat = False
    player.set_var("quest_clock", 20)
    assert player.flush_autosave() is True
    assert len(calls) == 1


def test_safe_room_with_living_enemy_does_not_autosave(monkeypatch):
    calls = _install_save_counter(monkeypatch)
    player = Player("河埠敌人", "散人")
    player.location = "northfront_wharf"
    player.set_var("quest_clock", 10)

    assert player._autosave_allowed() is False
    assert player.autosave() is True
    assert len(calls) == 0
    assert getattr(player, "_autosave_pending", False) is True


def test_autosave_and_manual_save_use_distinct_messages(tmp_path, capsys):
    player = Player("存档提示", "散人")
    player.location = "village_square"
    player.set_var("quest_clock", 0)
    target = str(tmp_path / "save.json")

    assert player.autosave(target) is True
    assert "游戏已自动保存" in capsys.readouterr().out

    player.set_var("quest_clock", 10)
    assert player.save_to_file(target) is True
    assert "[存档成功] 游戏进度已保存。" in capsys.readouterr().out
