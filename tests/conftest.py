"""测试全局隔离：无参存档一律重定向到临时文件，绝不触碰正式存档。"""
import os

import pytest

import engine
import player as player_module


@pytest.fixture(autouse=True)
def _isolate_official_save(tmp_path, monkeypatch):
    real_save = player_module.Player.save_to_file
    official = os.path.normcase(os.path.abspath(engine.SAVE_PATH))

    def guarded(self, filename=engine.SAVE_PATH, verbose=True, auto=False):
        if filename is None or os.path.normcase(os.path.abspath(str(filename))) == official:
            filename = str(tmp_path / "save.json")
        return real_save(self, filename, verbose, auto)

    monkeypatch.setattr(player_module.Player, "save_to_file", guarded)
