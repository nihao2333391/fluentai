import { randomUUID } from 'node:crypto'

import type { PickedModelFile } from '../shared/contracts'
import { type ValidatedModelFile, validateModelFile } from './model-file-validation'

export class ModelFileRegistry {
  private readonly files = new Map<string, ValidatedModelFile>()

  register(filePath: string): PickedModelFile {
    const file = validateModelFile(filePath)
    const fileToken = randomUUID()
    this.files.set(fileToken, file)
    return {
      fileToken,
      filePath: file.filePath,
      fileName: file.fileName,
      size: file.size,
      modifiedAt: file.modifiedAt,
      extension: file.extension,
    }
  }

  resolve(fileToken: string): ValidatedModelFile {
    const file = this.files.get(fileToken)
    if (!file) {
      throw new Error('Selected model file token is invalid or expired.')
    }
    return file
  }
}
