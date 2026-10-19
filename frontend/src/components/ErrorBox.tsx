import { t } from '../i18n'
import { errorMessage } from './errorMessage'

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="alert error" role="alert">
      <strong>{t('common.error')}: </strong>
      {errorMessage(error)}
      {onRetry && (
        <button className="btn small" style={{ marginInlineStart: 10 }} onClick={onRetry}>
          {t('common.retry')}
        </button>
      )}
    </div>
  )
}
