"""Alpha112: 指令表不得重复覆盖，客栈指令统一走同一分发器。"""
import ast
import inspect
from pathlib import Path

import main
import actions


def test_cmd_map_has_no_duplicate_literal_keys():
    source = Path(main.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "CMD_MAP" for t in n.targets)
    )
    keys = [k.value for k in node.value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
    assert len(keys) == len(set(keys))


def test_inn_synonyms_resolve_to_one_canonical_action():
    expected = {
        "住店": "inn_stay", "住宿": "inn_stay", "留宿": "inn_stay", "歇宿": "inn_stay",
        "吃饭": "inn_meal", "用餐": "inn_meal", "打尖": "inn_meal", "吃东西": "inn_meal",
        "喝茶": "inn_tea", "饮茶": "inn_tea",
        "听消息": "inn_rumor", "打听消息": "inn_rumor", "风声": "inn_rumor",
    }
    for raw, canonical in expected.items():
        assert main.parse_command(raw)[0] == canonical


def test_main_uses_shared_inn_handler_with_compatible_signature():
    assert main.handle_inn_service is actions.handle_inn_service
    params = list(inspect.signature(main.handle_inn_service).parameters)
    assert params[:3] == ["player", "action", "args"]
    assert "lodging" not in main.CMD_MAP.values()
    assert "meal" not in main.CMD_MAP.values()
