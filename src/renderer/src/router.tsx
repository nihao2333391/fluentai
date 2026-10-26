import { createHashRouter, Navigate } from 'react-router-dom'

import { AppLayout } from './app/AppLayout'
import { MeshingAutomationCreatePage } from './pages/MeshingAutomationCreatePage'
import { MeshingAutomationsPage } from './pages/MeshingAutomationsPage'
import { MeshingLiveSyncPage } from './pages/MeshingLiveSyncPage'
import { MyModelsPage } from './pages/MyModelsPage'
import { SettingsPage } from './pages/SettingsPage'

export const appRoutes = [
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/meshing" replace /> },
      { path: 'models', element: <MyModelsPage /> },
      { path: 'meshing', element: <MeshingAutomationsPage /> },
      {
        path: 'meshing/create',
        element: <MeshingAutomationCreatePage key="meshing-create" />,
      },
      {
        path: 'meshing/:id/edit',
        element: <MeshingAutomationCreatePage key="meshing-edit" />,
      },
      { path: 'meshing/live/:sessionId', element: <MeshingLiveSyncPage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: '*', element: <Navigate to="/meshing" replace /> },
    ],
  },
]

export const appRouter = createHashRouter(appRoutes)
