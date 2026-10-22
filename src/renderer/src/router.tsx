import { createHashRouter, Navigate } from 'react-router-dom'

import { AppLayout } from './app/AppLayout'
import { AutomationCreatePage } from './pages/AutomationCreatePage'
import { MeshingAutomationCreatePage } from './pages/MeshingAutomationCreatePage'
import { MeshingAutomationsPage } from './pages/MeshingAutomationsPage'
import { MyAutomationsPage } from './pages/MyAutomationsPage'
import { MyModelsPage } from './pages/MyModelsPage'
import { SettingsPage } from './pages/SettingsPage'

export const appRoutes = [
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/automations/create" replace /> },
      { path: 'automations/create', element: <AutomationCreatePage /> },
      { path: 'automations/:id/edit', element: <AutomationCreatePage /> },
      { path: 'automations/:id/duplicate', element: <AutomationCreatePage /> },
      { path: 'automations', element: <MyAutomationsPage /> },
      { path: 'models', element: <MyModelsPage /> },
      { path: 'meshing', element: <MeshingAutomationsPage /> },
      { path: 'meshing/create', element: <MeshingAutomationCreatePage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: '*', element: <Navigate to="/automations/create" replace /> },
    ],
  },
]

export const appRouter = createHashRouter(appRoutes)
