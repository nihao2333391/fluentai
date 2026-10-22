import { createHashRouter, Navigate } from 'react-router-dom'

import { AppLayout } from './app/AppLayout'
import { AutomationCreatePage } from './pages/AutomationCreatePage'
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
      { path: 'automations', element: <MyAutomationsPage /> },
      { path: 'models', element: <MyModelsPage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: '*', element: <Navigate to="/automations/create" replace /> },
    ],
  },
]

export const appRouter = createHashRouter(appRoutes)
