import { safeStorage } from 'electron'
import { join } from 'node:path'

import { CredentialStore } from './credential-store'

export function createElectronCredentialStore(
  userDataDirectory: string,
  fileName = 'fluent-credentials.json',
): CredentialStore {
  return new CredentialStore(join(userDataDirectory, 'secrets', fileName), {
    isAvailable: () => safeStorage.isAsyncEncryptionAvailable(),
    encryptString: (value) => safeStorage.encryptStringAsync(value),
    decryptString: async (value) => (await safeStorage.decryptStringAsync(value)).result,
  })
}
