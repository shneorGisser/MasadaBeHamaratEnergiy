import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ProjectsPage from './ProjectsPage'

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const json = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))

afterEach(() => vi.restoreAllMocks())

describe('ProjectsPage', () => {
  it('shows the empty state and disables create until a name is typed', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input)
      if (url.endsWith('/api/experiments')) return json([{ id: 'transformer3ph', version: 1, title_he: 'ניסוי 1', summary_he: '', manual_ref: '' }])
      return json([])
    })
    renderPage()
    expect(await screen.findByText(/אין עדיין פרויקטים/)).toBeInTheDocument()
    const btn = screen.getByRole('button', { name: 'צור פרויקט' })
    expect(btn).toBeDisabled()
    await userEvent.type(screen.getByPlaceholderText(/קבוצה 3/), 'קבוצה 7')
    expect(btn).toBeEnabled()
  })

  it('surfaces server errors instead of failing silently', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input)
      if (url.endsWith('/api/experiments')) return json([])
      return json({ error: { code: 'boom', message: 'database locked' } }, 500)
    })
    renderPage()
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('database locked'))
  })
})
