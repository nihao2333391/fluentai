import { describe, expect, it } from 'vitest'

import { resources } from './resources'

const flattenKeys = (value: object, prefix = ''): string[] =>
  Object.entries(value).flatMap(([key, item]) => {
    const path = prefix ? `${prefix}.${key}` : key
    return typeof item === 'object' && item !== null ? flattenKeys(item, path) : [path]
  })

describe('i18n resources', () => {
  it('keeps Chinese and English translation keys in sync', () => {
    expect(flattenKeys(resources.en.translation).sort()).toEqual(
      flattenKeys(resources.zh.translation).sort(),
    )
  })
})
