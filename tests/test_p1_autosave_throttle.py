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


def test_autosave_coalesces_within_three_world_ticks(monkeypatch):
    calls = _install_save_counter(monkeypatch)
    player = Player("存档节流", "散人")
    player.set_var("quest_clock", 10)

    assert player.autosave() is True
    assert len(calls) == 1

    player.set_var("quest_clock", 11)
    assert player.autosave() is True
    player.set_var("quest_clock", 12)
    assert player.autosave() is True
    assert len(calls) == 1
    assert getattr(player, "_autosave_pending", False) is True
    assert player.flush_autosave() is False

    player.set_var("quest_clock", 13)
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
