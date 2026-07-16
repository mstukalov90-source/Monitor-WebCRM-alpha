import type { LayerGroupConfig } from '../types'
import {
  DISTRICT_OKRUG_FIELD,
  DISTRICT_RAYON_FIELD,
  filterDistrictGeoJson,
  HOOD_BOUNDARIES_DISPLAY_NAME,
  normalizeRayonName,
} from '../types'

export function findHoodLayerKey(groups: LayerGroupConfig[]): string | null {
  for (const group of groups) {
    for (const layer of group.layers) {
      if (layer.display_name === HOOD_BOUNDARIES_DISPLAY_NAME) {
        return layer.layer_key
      }
    }
    if (group.groups.length) {
      const nested = findHoodLayerKey(group.groups)
      if (nested) return nested
    }
  }
  return null
}

export interface DistrictHoodMeta {
  /** Unique okrug_shor values, sorted. */
  okrugs: string[]
  /** Normalized rayon name → normalized okrug_shor. */
  rayonToOkrug: Record<string, string>
}

/** Build okrug list and rayon↔okrug map from hood GeoJSON (after НАО/ТАО filter). */
export function extractDistrictMeta(geojson: GeoJSON.FeatureCollection): DistrictHoodMeta {
  const filtered = filterDistrictGeoJson(geojson)
  const okrugSet = new Set<string>()
  const rayonToOkrug: Record<string, string> = {}

  for (const feature of filtered.features) {
    const rayon = normalizeRayonName(String(feature.properties?.[DISTRICT_RAYON_FIELD] ?? ''))
    const okrug = normalizeRayonName(String(feature.properties?.[DISTRICT_OKRUG_FIELD] ?? ''))
    if (okrug) okrugSet.add(okrug)
    if (rayon && okrug) rayonToOkrug[rayon] = okrug
  }

  return {
    okrugs: [...okrugSet].sort((a, b) => a.localeCompare(b, 'ru')),
    rayonToOkrug,
  }
}

/** Keep only features belonging to the given okrug_shor (empty = all). */
export function filterDistrictGeoJsonByOkrug(
  geojson: GeoJSON.FeatureCollection,
  okrug: string,
): GeoJSON.FeatureCollection {
  const okrugNorm = normalizeRayonName(okrug)
  if (!okrugNorm) return geojson
  return {
    ...geojson,
    features: geojson.features.filter(
      (feature) =>
        normalizeRayonName(String(feature.properties?.[DISTRICT_OKRUG_FIELD] ?? '')) === okrugNorm,
    ),
  }
}
