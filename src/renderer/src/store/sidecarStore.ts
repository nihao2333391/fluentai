import { create } from 'zustand'

import type { SidecarStatus } from '../../../shared/contracts'

interface SidecarStore {
  status: SidecarStatus
  setStatus: (status: SidecarStatus) => void
}

export const useSidecarStore = create<SidecarStore>((set) => ({
  status: {
    state: 'starting',
    message: 'Waiting for the Electron sidecar bridge.',
  },
  setStatus: (status) => set({ status }),
}))
