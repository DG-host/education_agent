# -*- coding: utf-8 -*-
"""内容图谱知识网络投影：计数、结构、排除项与确定性。"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

import graph_model  # noqa: E402
from common import load_json  # noqa: E402


class TestGraphModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = load_json(os.path.join(ROOT, "out", "content_map.json"))
        cls.graph = graph_model.build(cls.content)

    def test_counts(self):
        meta = self.graph["meta"]
        self.assertEqual(self.graph["version"], "content_graph/1")
        self.assertEqual(meta["node_counts"], {
            "topic": 3, "indicator": 9, "standard": 3, "material": 57, "total": 72,
        })
        self.assertEqual(meta["edge_counts"], {
            "topic_indicator": 9, "indicator_standard": 9,
            "indicator_material": 63, "topic_progression": 2, "total": 83,
        })
        self.assertEqual(meta["skeleton_nodes"], 15)
        self.assertEqual(meta["skeleton_edges"], 20)
        self.assertEqual(meta["resources"], 57)

    def test_structure(self):
        nodes = {n["id"]: n for n in self.graph["nodes"]}
        self.assertEqual(len(nodes), len(self.graph["nodes"]))
        self.assertEqual(len({e["id"] for e in self.graph["edges"]}), len(self.graph["edges"]))
        degree = {node_id: 0 for node_id in nodes}
        for edge in self.graph["edges"]:
            self.assertIn(edge["source"], nodes)
            self.assertIn(edge["target"], nodes)
            degree[edge["source"]] += 1
            degree[edge["target"]] += 1
        self.assertTrue(all(value > 0 for value in degree.values()), degree)

        for topic in ("T01", "T02", "T03"):
            self.assertIn("topic:" + topic, nodes)
        self.assertIn("topic_progression:topic:T01->topic:T02", {e["id"] for e in self.graph["edges"]})
        self.assertIn("topic_progression:topic:T02->topic:T03", {e["id"] for e in self.graph["edges"]})

        for node in self.graph["nodes"]:
            if node["kind"] == "indicator":
                self.assertTrue(node.get("cr_id"), node)
                self.assertTrue(any(e["source"] == node["id"] and e["kind"] == "indicator_standard"
                                    for e in self.graph["edges"]))
                self.assertTrue(any(e["source"] == node["id"] and e["kind"] == "indicator_material"
                                    for e in self.graph["edges"]))
        l01 = [e for e in self.graph["edges"]
               if e["kind"] == "indicator_material" and e["target"] == "material:L01"]
        self.assertEqual(len(l01), 3)

    def test_excluded_materials(self):
        excluded = self.graph["meta"]["excluded_materials"]
        self.assertEqual([x["material_id"] for x in excluded],
                         ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08"])
        node_ids = {n["id"] for n in self.graph["nodes"]}
        for item in excluded:
            self.assertNotIn("material:" + item["material_id"], node_ids)
            self.assertIn("未被任何指标引用", item["reason"])

    def test_deterministic_and_sorted(self):
        again = graph_model.build(self.content)
        self.assertEqual(again, self.graph)
        order = ["topic", "indicator", "standard", "material"]
        keys = [(order.index(n["kind"]), n["ref"]) for n in self.graph["nodes"]]
        self.assertEqual(keys, sorted(keys))
        edge_order = ["topic_indicator", "indicator_standard", "indicator_material", "topic_progression"]
        edge_keys = [(edge_order.index(e["kind"]), e["source"], e["target"]) for e in self.graph["edges"]]
        self.assertEqual(edge_keys, sorted(edge_keys))


if __name__ == "__main__":
    unittest.main()
