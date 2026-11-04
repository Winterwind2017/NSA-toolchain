"""从上游 CAD-Agent-Hub 原样搬来的纯几何测试（只改 import 前缀）。

来源：MCP/Solidworks/tests/test_part_generators.py
目的：证明 hub 里 vendored 的 hubsw/* 不是残缺副本——上游有多少断言，这边就跑多少。
"""

from __future__ import annotations

import unittest

from nsa_mcp_hub.adapters.hubsw.feature_graph import compile_feature_graph
from nsa_mcp_hub.adapters.hubsw.part_generators import build_parametric_part_graph


class PartGeneratorTests(unittest.TestCase):
    def test_all_common_part_generators_compile(self) -> None:
        cases = {
            "block": {"length_mm": 80, "width_mm": 40, "height_mm": 12},
            "cylinder": {"diameter_mm": 30, "length_mm": 70},
            "tube": {"outer_diameter_mm": 50, "inner_diameter_mm": 42, "length_mm": 100},
            "flange": {
                "outer_diameter_mm": 120,
                "bore_diameter_mm": 40,
                "thickness_mm": 12,
                "bolt_circle_diameter_mm": 90,
                "bolt_hole_diameter_mm": 10,
                "bolt_count": 6,
            },
            "stepped_shaft": {
                "steps": [
                    {"diameter_mm": 40, "length_mm": 50},
                    {"diameter_mm": 25, "length_mm": 35},
                ]
            },
        }
        for part_type, parameters in cases.items():
            with self.subTest(part_type=part_type):
                graph = build_parametric_part_graph(part_type, parameters)
                plan = compile_feature_graph(graph)
                self.assertGreaterEqual(len(plan), 3)
                self.assertEqual(graph["metadata"]["part_type"], part_type)

    def test_flange_holes_are_created_in_one_cut_sketch(self) -> None:
        graph = build_parametric_part_graph("flange", {"bolt_count": 8})
        hole_sketch = next(item for item in graph["features"] if item["name"] == "FlangeHoleSketch")
        self.assertEqual(len(hole_sketch["entities"]), 9)


if __name__ == "__main__":
    unittest.main()
