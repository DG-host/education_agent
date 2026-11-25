"""内容图谱的知识网络投影。

只把 content_map 中已经写明的关系变成节点和边：
主题包含指标、指标对应课标、指标可用材料、主题递进。
不猜测教材切片归属，不生成语义相似度边。
"""

from __future__ import annotations

from collections import Counter


GRAPH_VERSION = "content_graph/1"
KIND_ORDER = ("topic", "indicator", "standard", "material")
EDGE_ORDER = ("topic_indicator", "indicator_standard", "indicator_material", "topic_progression")


def _text(value):
    return str(value or "").strip()


def _add_node(nodes, seen, node):
    node_id = node.get("id")
    if not node_id or node_id in seen:
        return
    seen[node_id] = node
    nodes.append(node)


def _add_edge(edges, seen, source, target, kind, label):
    if not source or not target:
        return
    edge_id = "%s:%s->%s" % (kind, source, target)
    if edge_id in seen:
        return
    seen.add(edge_id)
    edges.append({
        "id": edge_id,
        "source": source,
        "target": target,
        "kind": kind,
        "label": label,
    })


def build(content_map):
    """把 content_map 投影为可直接渲染的图和计数元数据。"""
    content_map = content_map if isinstance(content_map, dict) else {}
    topics = [t for t in (content_map.get("topics") or []) if isinstance(t, dict)]
    materials = [m for m in (content_map.get("materials_index") or []) if isinstance(m, dict)]
    topics.sort(key=lambda t: _text(t.get("topic_id")))
    materials.sort(key=lambda m: _text(m.get("material_id")))

    material_by_id = {}
    for material in materials:
        material_id = _text(material.get("material_id"))
        if material_id:
            material_by_id[material_id] = material

    nodes = []
    node_seen = {}
    edges = []
    edge_seen = set()
    referenced = set()

    for topic in topics:
        topic_id = _text(topic.get("topic_id"))
        if not topic_id:
            continue
        _add_node(nodes, node_seen, {
            "id": "topic:" + topic_id,
            "kind": "topic",
            "ref": topic_id,
            "label": _text(topic.get("topic")) or topic_id,
            "goal": _text(topic.get("goal")),
        })
        for indicator in sorted((topic.get("indicators") or []), key=lambda x: _text(x.get("indicator_id"))):
            if not isinstance(indicator, dict):
                continue
            indicator_id = _text(indicator.get("indicator_id"))
            if not indicator_id:
                continue
            standard = indicator.get("standard") or {}
            cr_id = _text(standard.get("cr_id")) if isinstance(standard, dict) else ""
            _add_node(nodes, node_seen, {
                "id": "indicator:" + indicator_id,
                "kind": "indicator",
                "ref": indicator_id,
                "label": _text(indicator.get("observation")) or indicator_id,
                "topic_id": topic_id,
                "cr_id": cr_id,
                "textbook_pages": _text(indicator.get("textbook_pages")),
            })
            _add_edge(edges, edge_seen, "topic:" + topic_id, "indicator:" + indicator_id,
                      "topic_indicator", "包含指标")
            if cr_id:
                _add_node(nodes, node_seen, {
                    "id": "standard:" + cr_id,
                    "kind": "standard",
                    "ref": cr_id,
                    "label": "课标 " + cr_id,
                    "pdf_pages": _text(standard.get("pdf_pages")),
                    "body_pages": _text(standard.get("body_pages")),
                })
                _add_edge(edges, edge_seen, "indicator:" + indicator_id, "standard:" + cr_id,
                          "indicator_standard", "对应课标")
            for material_id in (indicator.get("material_ids") or []):
                material_id = _text(material_id)
                if not material_id:
                    continue
                referenced.add(material_id)
                material = material_by_id.get(material_id) or {}
                _add_node(nodes, node_seen, {
                    "id": "material:" + material_id,
                    "kind": "material",
                    "ref": material_id,
                    "label": material_id,
                    "material_type": _text(material.get("type")),
                    "topic_id": _text(material.get("topic_id")),
                    "question_type": _text(material.get("question_type")),
                    "max_score": material.get("max_score"),
                    "node_scope": list(material.get("node_scope") or []),
                    "indicator_ids": [],
                })
                node = node_seen["material:" + material_id]
                if indicator_id not in node["indicator_ids"]:
                    node["indicator_ids"].append(indicator_id)
                    node["indicator_ids"].sort()
                _add_edge(edges, edge_seen, "indicator:" + indicator_id, "material:" + material_id,
                          "indicator_material", "可用材料")

    for left, right in zip(topics, topics[1:]):
        left_id = _text(left.get("topic_id"))
        right_id = _text(right.get("topic_id"))
        _add_edge(edges, edge_seen, "topic:" + left_id, "topic:" + right_id,
                  "topic_progression", "学习进阶")

    excluded = []
    for material in materials:
        material_id = _text(material.get("material_id"))
        if not material_id or material_id in referenced:
            continue
        excluded.append({
            "material_id": material_id,
            "type": _text(material.get("type")) or "未分类",
            "reason": "未被任何指标引用，不生成猜测挂接",
        })
    excluded.sort(key=lambda x: x["material_id"])

    nodes.sort(key=lambda n: (KIND_ORDER.index(n["kind"]), n["ref"]))
    edges.sort(key=lambda e: (EDGE_ORDER.index(e["kind"]), e["source"], e["target"]))
    node_counts = Counter(n["kind"] for n in nodes)
    edge_counts = Counter(e["kind"] for e in edges)
    resources = node_counts.get("material", 0)
    skeleton_edges = len(edges) - edge_counts.get("indicator_material", 0)

    return {
        "version": GRAPH_VERSION,
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "node_counts": {
                "topic": node_counts.get("topic", 0),
                "indicator": node_counts.get("indicator", 0),
                "standard": node_counts.get("standard", 0),
                "material": resources,
                "total": len(nodes),
            },
            "edge_counts": {
                "topic_indicator": edge_counts.get("topic_indicator", 0),
                "indicator_standard": edge_counts.get("indicator_standard", 0),
                "indicator_material": edge_counts.get("indicator_material", 0),
                "topic_progression": edge_counts.get("topic_progression", 0),
                "total": len(edges),
            },
            "skeleton_nodes": len(nodes) - resources,
            "skeleton_edges": skeleton_edges,
            "resources": resources,
            "excluded_materials": excluded,
        },
    }
