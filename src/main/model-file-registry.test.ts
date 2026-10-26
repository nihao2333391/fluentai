// @vitest-environment node

import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { afterEach, describe, expect, it } from 'vitest'

import { ModelFileRegistry } from './model-file-registry'

const temporaryDirectories: string[] = []

const makeTemporaryDirectory = (): string => {
  const directory = mkdtempSync(join(tmpdir(), 'fluent-ai-files-'))
  temporaryDirectories.push(directory)
  return directory
}

afterEach(() => {
  while (temporaryDirectories.length > 0) {
    const directory = temporaryDirectories.pop()
    if (directory) {
      rmSync(directory, { recursive: true, force: true })
    }
  }
})

describe('ModelFileRegistry', () => {
  it('validates and registers a Fluent case file', () => {
    const directory = makeTemporaryDirectory()
    const filePath = join(directory, 'case.cas.h5')
    writeFileSync(filePath, 'case content')

    const registry = new ModelFileRegistry()
    const selected = registry.register(filePath)

    expect(selected.fileName).toBe('case.cas.h5')
    expect(selected.extension).toBe('.cas.h5')
    expect(selected.size).toBeGreaterThan(0)
    expect(selected.fileToken).toMatch(/[0-9a-f-]{36}/)
    expect(registry.resolve(selected.fileToken).filePath).toBe(selected.filePath)
  })

  it('accepts SpaceClaim exchange and additional CAD reader formats', () => {
    const directory = makeTemporaryDirectory()
    const registry = new ModelFileRegistry()

    for (const fileName of ['middle.scdocx', 'long-flow.stpz', 'part.jt', 'body.x_t']) {
      const filePath = join(directory, fileName)
      writeFileSync(filePath, 'geometry content')
      expect(registry.register(filePath).fileName).toBe(fileName)
    }
  })

  it('rejects unsupported, empty, missing, and directory paths', () => {
    const directory = makeTemporaryDirectory()
    const registry = new ModelFileRegistry()

    const textFile = join(directory, 'case.txt')
    writeFileSync(textFile, 'not a model')
    expect(() => registry.register(textFile)).toThrow(/must use/)

    const emptyFile = join(directory, 'empty.cas')
    writeFileSync(emptyFile, '')
    expect(() => registry.register(emptyFile)).toThrow(/empty/)

    expect(() => registry.register(join(directory, 'missing.cas'))).toThrow()

    const modelDirectory = join(directory, 'folder.cas')
    mkdirSync(modelDirectory)
    expect(() => registry.register(modelDirectory)).toThrow(/regular file/)
  })

  it('rejects unknown file tokens', () => {
    const registry = new ModelFileRegistry()
    expect(() => registry.resolve('unknown-token')).toThrow(/invalid or expired/)
  })
})
