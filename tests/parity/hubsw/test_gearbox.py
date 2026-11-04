"""从上游 CAD-Agent-Hub 原样搬来的纯几何测试（只改 import 前缀）。

来源：MCP/Solidworks/tests/test_gearbox.py
目的：证明 hub 里 vendored 的 hubsw/* 不是残缺副本——上游有多少断言，这边就跑多少。
"""

from __future__ import annotations

import unittest

from nsa_mcp_hub.adapters.hubsw.feature_graph import compile_feature_graph
from nsa_mcp_hub.adapters.hubsw.gearbox import build_two_stage_reducer_graph


class GearboxTests(unittest.TestCase):
    def test_two_stage_reducer_compiles_with_expected_ratios(self) -> None:
        graph = build_two_stage_reducer_graph()
        plan = compile_feature_graph(graph)

        self.assertEqual(graph["metadata"]["total_ratio"], 6.0)
        self.assertEqual(graph["metadata"]["stage1_center_distance_mm"], 60.0)
        self.assertEqual(graph["metadata"]["stage2_center_distance_mm"], 80.0)
        self.assertIn("reference_plane_offset", {step["operation"] for step in plan})
        self.assertEqual(plan[-1]["name"], "ReducerKeywayCut")


if __name__ == "__main__":
    unittest.main()
