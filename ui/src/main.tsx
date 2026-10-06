import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SnackbarProvider } from 'notistack'
import App from './App'

const queryClient = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } } })

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <SnackbarProvider maxSnack={4} anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }} autoHideDuration={4000}>
        <App />
      </SnackbarProvider>
    </QueryClientProvider>
  </StrictMode>,
)
