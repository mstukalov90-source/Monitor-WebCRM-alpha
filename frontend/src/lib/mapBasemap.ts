export const MAP_BASEMAP_ATTRIBUTION = 'МГГТ'

export const MAP_BASEMAPS = [
  {
    id: '1_2000',
    name: '1:2000',
    url: 'http://ngtst.mggt:8080/api/component/render/tile?resource=232992&nd=204&z={z}&x={x}&y={y}',
  },
  {
    id: 'satellite',
    name: 'Спутник',
    url: 'http://ngtst.mggt:8080/api/component/render/tile?resource=303242&nd=204&z={z}&x={x}&y={y}',
  },
  {
    id: 'schema',
    name: 'Схема',
    url: 'http://ngtst.mggt:8080/api/component/render/tile?resource=248465&nd=204&z={z}&x={x}&y={y}',
  },
] as const

export type BasemapId = (typeof MAP_BASEMAPS)[number]['id']

export const DEFAULT_BASEMAP_ID: BasemapId = 'schema'
