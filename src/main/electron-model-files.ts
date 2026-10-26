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
          name: 'Fluent case, mesh, and geometry files',
          extensions: [
            'cas',
            'cas.h5',
            'msh',
            'msh.h5',
            'dsco',
            'scdoc',
            'scdocx',
            'step',
            'stp',
            'stpz',
            'iges',
            'igs',
            'jt',
            '3dxml',
            'catpart',
            'catproduct',
            'sldprt',
            'sldasm',
            'ipt',
            'iam',
            'prt',
            'asm',
            'par',
            'stl',
            'pmdb',
            'fmd',
            'tgf',
            'x_t',
            'x_b',
            'sat',
            'sab',
          ],
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
