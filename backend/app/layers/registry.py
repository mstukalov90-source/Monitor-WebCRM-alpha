"""Layer registry from layers_config.json."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.config import load_layers_config


def _slugify(name: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", name, flags=re.UNICODE)
    slug = re.sub(r"[\s_]+", "_", slug.strip())
    return slug.lower() or "layer"


@dataclass
class LayerDef:
    layer_key: str
    display_name: str
    schema: str
    table_name: str
    geometry_column: str
    geometry_type: str
    symbology: dict[str, Any]
    sql_filter: str | None = None
    primary_key: str | None = None
    placeholder: bool = False
    group_path: list[str] = field(default_factory=list)

    @property
    def qualified_table(self) -> str:
        return f'"{self.schema}"."{self.table_name}"'


@dataclass
class LayerGroupNode:
    name: str
    default_visibility: bool = True
    groups: list[LayerGroupNode] = field(default_factory=list)
    layers: list[LayerDef] = field(default_factory=list)


class LayerRegistry:
    def __init__(self) -> None:
        self.root_groups: list[LayerGroupNode] = []
        self.by_key: dict[str, LayerDef] = {}
        self.by_display_name: dict[str, LayerDef] = {}
        self._build()

    def _register_layer(self, layer_cfg: dict[str, Any], group_path: list[str]) -> None:
        display_name = layer_cfg.get("display_name", "")
        if not display_name:
            return
        if layer_cfg.get("placeholder"):
            return
        table_name = layer_cfg.get("table_name")
        schema = layer_cfg.get("schema")
        geom_col = layer_cfg.get("geometry_column")
        if not table_name or not schema or not geom_col:
            return

        base_key = _slugify(display_name)
        layer_key = base_key
        n = 2
        while layer_key in self.by_key:
            layer_key = f"{base_key}_{n}"
            n += 1

        layer = LayerDef(
            layer_key=layer_key,
            display_name=display_name,
            schema=schema,
            table_name=table_name,
            geometry_column=geom_col,
            geometry_type=layer_cfg.get("geometry_type", "point"),
            symbology=layer_cfg.get("symbology", {}),
            sql_filter=layer_cfg.get("sql_filter"),
            primary_key=layer_cfg.get("primary_key"),
            placeholder=False,
            group_path=list(group_path),
        )
        self.by_key[layer_key] = layer
        self.by_display_name[display_name] = layer

    def _parse_group(self, group_cfg: dict[str, Any], path: list[str]) -> LayerGroupNode:
        name = group_cfg.get("group_name", "")
        current_path = path + [name] if name else path
        node = LayerGroupNode(
            name=name,
            default_visibility=group_cfg.get("default_visibility", True),
        )
        for layer_cfg in group_cfg.get("layers", []):
            self._register_layer(layer_cfg, current_path)
            display_name = layer_cfg.get("display_name", "")
            if display_name and not layer_cfg.get("placeholder"):
                layer = self.by_display_name.get(display_name)
                if layer:
                    node.layers.append(layer)
        for child in group_cfg.get("groups", []):
            child_node = self._parse_group(child, current_path)
            node.groups.append(child_node)
        return node

    def _build(self) -> None:
        config = load_layers_config()
        for group_cfg in config.get("layer_groups", []):
            self.root_groups.append(self._parse_group(group_cfg, []))

    def resolve_layer_names(self, layer_names: list[str]) -> tuple[list[LayerDef], list[str]]:
        found: list[LayerDef] = []
        missing: list[str] = []
        seen: set[str] = set()
        for name in layer_names:
            layer = self.by_display_name.get(name)
            if layer and layer.layer_key not in seen:
                found.append(layer)
                seen.add(layer.layer_key)
            elif layer is None:
                missing.append(name)
        return found, missing

    def resolve_group_layers(self, group_names: list[str]) -> tuple[list[LayerDef], list[str]]:
        found: list[LayerDef] = []
        missing: list[str] = []
        seen: set[str] = set()

        def collect_from_node(node: LayerGroupNode) -> None:
            for layer in node.layers:
                if layer.layer_key not in seen:
                    found.append(layer)
                    seen.add(layer.layer_key)
            for child in node.groups:
                collect_from_node(child)

        def find_group(nodes: list[LayerGroupNode], name: str) -> LayerGroupNode | None:
            for node in nodes:
                if node.name == name:
                    return node
                found_node = find_group(node.groups, name)
                if found_node:
                    return found_node
            return None

        for group_name in group_names:
            node = find_group(self.root_groups, group_name)
            if node is None:
                missing.append(group_name)
            else:
                collect_from_node(node)
        return found, missing

    def resolve_subgroup_layers(
        self, layer_names: list[str], group_names: list[str]
    ) -> tuple[list[LayerDef], list[str]]:
        found1, miss1 = self.resolve_layer_names(layer_names)
        found2, miss2 = self.resolve_group_layers(group_names)
        seen: set[str] = set()
        merged: list[LayerDef] = []
        for layer in found1 + found2:
            if layer.layer_key not in seen:
                merged.append(layer)
                seen.add(layer.layer_key)
        return merged, miss1 + miss2

    def to_config_tree(self) -> list[dict[str, Any]]:
        def node_to_dict(node: LayerGroupNode) -> dict[str, Any]:
            return {
                "name": node.name,
                "default_visibility": node.default_visibility,
                "layers": [
                    {
                        "layer_key": l.layer_key,
                        "display_name": l.display_name,
                        "geometry_type": l.geometry_type,
                        "symbology": l.symbology,
                        "placeholder": l.placeholder,
                    }
                    for l in node.layers
                ],
                "groups": [node_to_dict(g) for g in node.groups],
            }

        return [node_to_dict(g) for g in self.root_groups]


_registry: LayerRegistry | None = None


def get_registry() -> LayerRegistry:
    global _registry
    if _registry is None:
        _registry = LayerRegistry()
    return _registry
