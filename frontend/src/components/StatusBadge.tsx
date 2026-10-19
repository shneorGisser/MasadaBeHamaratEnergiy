import type { RunStatus } from '../api/types'
import { t } from '../i18n'

export default function StatusBadge({ status }: { status: RunStatus }) {
  const cls = status === 'success' ? 'ok' : status === 'success_with_warnings' ? 'warn' : 'err'
  return (
    <span className={`badge ${cls}`} data-testid="run-status" data-status={status}>
      {t(`status.${status}`)}
    </span>
  )
}
