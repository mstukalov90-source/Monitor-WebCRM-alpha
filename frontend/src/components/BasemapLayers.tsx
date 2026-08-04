import { LayersControl, TileLayer } from 'react-leaflet'
import {
  DEFAULT_BASEMAP_ID,
  MAP_BASEMAP_ATTRIBUTION,
  MAP_BASEMAPS,
} from '../lib/mapBasemap'

const MAP_MAX_ZOOM = 19

export function BasemapLayers() {
  return (
    <LayersControl position="topright">
      {MAP_BASEMAPS.map((basemap) => (
        <LayersControl.BaseLayer
          key={basemap.id}
          name={basemap.name}
          checked={basemap.id === DEFAULT_BASEMAP_ID}
        >
          <TileLayer
            url={basemap.url}
            attribution={MAP_BASEMAP_ATTRIBUTION}
            maxZoom={MAP_MAX_ZOOM}
          />
        </LayersControl.BaseLayer>
      ))}
    </LayersControl>
  )
}
