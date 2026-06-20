import type { LayerConfig, LayerGroupConfig } from '../types'

interface LayerControlProps {
  groups: LayerGroupConfig[]
  visibleKeys: Set<string>
  onToggle: (layerKey: string, visible: boolean) => void
}

function LayerGroup({
  group,
  visibleKeys,
  onToggle,
  depth = 0,
}: {
  group: LayerGroupConfig
  visibleKeys: Set<string>
  onToggle: (layerKey: string, visible: boolean) => void
  depth?: number
}) {
  return (
    <div className="layer-group" style={{ marginLeft: depth * 12 }}>
      {group.name && <div className="layer-group-title">{group.name}</div>}
      {group.layers.map((layer) => (
        <label key={layer.layer_key} className="layer-item">
          <input
            type="checkbox"
            checked={visibleKeys.has(layer.layer_key)}
            onChange={(e) => onToggle(layer.layer_key, e.target.checked)}
          />
          <span>{layer.display_name}</span>
        </label>
      ))}
      {group.groups.map((child) => (
        <LayerGroup
          key={child.name}
          group={child}
          visibleKeys={visibleKeys}
          onToggle={onToggle}
          depth={depth + 1}
        />
      ))}
    </div>
  )
}

export function collectDefaultVisible(groups: LayerGroupConfig[]): Set<string> {
  const keys = new Set<string>()
  const walk = (nodes: LayerGroupConfig[]) => {
    nodes.forEach((g) => {
      if (g.default_visibility !== false) {
        g.layers.forEach((l) => keys.add(l.layer_key))
      }
      walk(g.groups)
    })
  }
  walk(groups)
  return keys
}

export function flattenLayers(groups: LayerGroupConfig[]): LayerConfig[] {
  const result: LayerConfig[] = []
  const walk = (nodes: LayerGroupConfig[]) => {
    nodes.forEach((g) => {
      result.push(...g.layers)
      walk(g.groups)
    })
  }
  walk(groups)
  return result
}

export function LayerControl({ groups, visibleKeys, onToggle }: LayerControlProps) {
  return (
    <div className="layer-control">
      <h3>Слои</h3>
      {groups.map((group) => (
        <LayerGroup key={group.name} group={group} visibleKeys={visibleKeys} onToggle={onToggle} />
      ))}
    </div>
  )
}
