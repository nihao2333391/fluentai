import { realpathSync, statSync } from 'node:fs'
import { basename } from 'node:path'

export const ALLOWED_MODEL_EXTENSIONS = ['.cas', '.cas.h5', '.msh', '.msh.h5'] as const

export interface ValidatedModelFile {
  filePath: string
  fileName: string
  size: number
  modifiedAt: string
  extension: (typeof ALLOWED_MODEL_EXTENSIONS)[number]
}

export function validateModelFile(filePath: string): ValidatedModelFile {
  const canonicalPath = realpathSync.native(filePath)
  const stat = statSync(canonicalPath)
  if (!stat.isFile()) {
    throw new Error(`Selected path is not a regular file: ${canonicalPath}`)
  }
  if (stat.size <= 0) {
    throw new Error(`Selected model file is empty: ${canonicalPath}`)
  }

  const lowerPath = canonicalPath.toLowerCase()
  const extension = ALLOWED_MODEL_EXTENSIONS.find((value) => lowerPath.endsWith(value))
  if (!extension) {
    throw new Error('Model file must use .cas, .cas.h5, .msh, or .msh.h5.')
  }

  return {
    filePath: canonicalPath,
    fileName: basename(canonicalPath),
    size: stat.size,
    modifiedAt: stat.mtime.toISOString(),
    extension,
  }
}
