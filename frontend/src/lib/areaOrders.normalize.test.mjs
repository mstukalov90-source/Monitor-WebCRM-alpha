/**
 * Node built-in test: normalizeRayonName + ordersForRayon matching for YuAO hood artifacts.
 * Run: node --test frontend/src/lib/areaOrders.normalize.test.mjs
 *
 * Mirrors frontend/src/types.ts normalizeRayonName (keep in sync).
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

function normalizeRayonName(value) {
  return value.replace(/\s+/g, ' ').trim().replace(/\s*-\s*/g, '-')
}

function ordersForRayon(groups, rayonName) {
  const key = normalizeRayonName(rayonName)
  const group = groups.find((g) => normalizeRayonName(g.rayon) === key)
  return group?.orders ?? []
}

describe('normalizeRayonName', () => {
  it('maps YuAO hood CR/LF and hyphen-space names to tasks_area form', () => {
    const cases = [
      ['Бирюлево \r\nВосточное', 'Бирюлево Восточное'],
      ['Москворечье-  Сабурово', 'Москворечье-Сабурово'],
      ['Нагатино-\r\nСадовники', 'Нагатино-Садовники'],
      ['Орехово-\r\nБорисово \r\nСеверное', 'Орехово-Борисово Северное'],
      ['Чертаново \r\n Южное', 'Чертаново Южное'],
    ]
    for (const [raw, expected] of cases) {
      assert.equal(normalizeRayonName(raw), expected)
    }
  })
})

describe('ordersForRayon', () => {
  it('finds orders when hood rayon has CR/LF and group has clean tasks_area name', () => {
    const groups = [
      {
        rayon: 'Нагатино-Садовники',
        orders: [{ task_key: 'a', attributes: { task_number: '1' } }],
      },
      {
        rayon: 'Орехово-Борисово Северное',
        orders: [{ task_key: 'b', attributes: { task_number: '2' } }],
      },
    ]
    assert.equal(ordersForRayon(groups, 'Нагатино-\r\nСадовники').length, 1)
    assert.equal(ordersForRayon(groups, 'Орехово-\r\nБорисово \r\nСеверное')[0].task_key, 'b')
    assert.equal(ordersForRayon(groups, 'Братеево').length, 0)
  })
})
