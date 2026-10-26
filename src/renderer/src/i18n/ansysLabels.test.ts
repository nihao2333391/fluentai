import { beforeEach, describe, expect, it } from 'vitest'

import i18n from './index'
import { localizedAnsysTerm, localizedAnsysValue } from './ansysLabels'

describe('ANSYS label localization', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('zh')
  })

  it('uses ANSYS Fluent Chinese terms for the Watertight workflow', () => {
    expect(localizedAnsysTerm('Import Geometry')).toBe('导入几何模型')
    expect(localizedAnsysTerm('Generate the Surface Mesh')).toBe('生成表面网格')
    expect(localizedAnsysTerm('Minimum Size')).toBe('最小尺寸')
    expect(localizedAnsysTerm('Target Mesh Size')).toBe('目标网格尺寸')
    expect(localizedAnsysValue('Curvature & Proximity')).toBe('曲率与邻近')
    expect(localizedAnsysValue('smooth-transition')).toBe('平滑过渡')
  })

  it('returns the original Fluent labels in English mode', async () => {
    await i18n.changeLanguage('en')

    expect(localizedAnsysTerm('Import Geometry')).toBe('Import Geometry')
    expect(localizedAnsysTerm('Minimum Size')).toBe('Minimum Size')
    expect(localizedAnsysValue('Curvature & Proximity')).toBe('Curvature & Proximity')
    expect(localizedAnsysValue('smooth-transition')).toBe('smooth-transition')
  })
})
