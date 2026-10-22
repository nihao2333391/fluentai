import '@ant-design/v5-patch-for-react-19'

import { RouterProvider } from 'react-router-dom'

import { AppProviders } from './app/AppProviders'
import { appRouter } from './router'

export default function App() {
  return (
    <AppProviders>
      <RouterProvider router={appRouter} />
    </AppProviders>
  )
}
