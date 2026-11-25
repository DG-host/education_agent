# -*- coding: utf-8 -*-
"""AgentContext：一次运行的工作目录、产物与哈希。"""
from __future__ import annotations

import hashlib
import os


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class AgentContext:
    def __init__(self, root, trace_path, dry_run=False):
        self.root = os.path.abspath(root)
        self.trace_path = trace_path
        self.dry_run = dry_run
        self.artifacts = {}

    def path(self, rel):
        return os.path.join(self.root, rel.replace("/", os.sep))

    def exists(self, rel):
        return os.path.exists(self.path(rel))

    def sha(self, rel):
        p = self.path(rel)
        return sha256(p) if os.path.exists(p) else None

    def record(self, rel):
        digest = self.sha(rel)
        if digest:
            self.artifacts[rel] = digest
        return digest
