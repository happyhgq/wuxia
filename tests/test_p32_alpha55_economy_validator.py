"""Alpha55：数据校验器必须检查跨文件经济链，而不只是 JSON 引用。"""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
import data_validator


class Alpha55EconomyValidatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data_dir = os.path.join(self.temp.name, "data")
        shutil.copytree(os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"), self.data_dir)
        self.original_data_dir = data_validator.DATA_DIR
        data_validator.DATA_DIR = self.data_dir

    def tearDown(self):
        data_validator.DATA_DIR = self.original_data_dir
        self.temp.cleanup()

    def _write_json(self, relpath, value):
        with open(os.path.join(self.data_dir, relpath), "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)

    def _validate(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = data_validator.main()
        return result, out.getvalue()

    def test_current_economy_config_passes_cross_file_validation(self):
        result, output = self._validate()
        self.assertEqual(result, 0, output)
        self.assertIn("DATA VALIDATION: PASS", output)

    def test_gatherer_item_mismatch_is_detected(self):
        path = os.path.join(self.data_dir, "economy", "gatherers.json")
        with open(path, encoding="utf-8") as f:
            gatherers = json.load(f)
        gatherers["樵夫老周"]["item"] = "草药"
        self._write_json("economy/gatherers.json", gatherers)
        result, output = self._validate()
        self.assertEqual(result, 1)
        self.assertIn("产出物品与资源点", output)

    def test_caravan_route_to_missing_room_is_detected(self):
        path = os.path.join(self.data_dir, "economy", "caravans.json")
        with open(path, encoding="utf-8") as f:
            caravans = json.load(f)
        caravans["北路商队"]["route"].append("不存在的房间")
        self._write_json("economy/caravans.json", caravans)
        result, output = self._validate()
        self.assertEqual(result, 1)
        self.assertIn("路线房间不存在", output)


if __name__ == "__main__":
    unittest.main()
