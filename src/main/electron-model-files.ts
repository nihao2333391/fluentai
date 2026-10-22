import { BrowserWindow, dialog } from 'electron'

import type { PickedModelFile } from '../shared/contracts'
import { ModelFileRegistry } from './model-file-registry'

export class ElectronModelFilePicker {
  constructor(private readonly registry: ModelFileRegistry) {}

  async pickFile(parent: BrowserWindow | null): Promise<PickedModelFile | null> {
    const options: Electron.OpenDialogOptions = {
      title: 'Select Fluent model file',
      properties: ['openFile'],
      filters: [
        {
          name: 'Fluent case and mesh files',
          extensions: ['cas', 'cas.h5', 'msh', 'msh.h5'],
        },
      ],
    }
    const result = parent
      ? await dialog.showOpenDialog(parent, options)
      : await dialog.showOpenDialog(options)
    if (result.canceled || result.filePaths.length === 0) {
      return null
    }
    return this.registry.register(result.filePaths[0])
  }
}
