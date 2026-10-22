import { useTranslation } from 'react-i18next'

import { EmptyState, PageContent } from '../components/PageState'

export function AutomationCreatePage() {
  const { t } = useTranslation()
  return (
    <PageContent
      title={t('pages.automationCreate.title')}
      description={t('pages.automationCreate.description')}
    >
      <EmptyState
        title={t('pages.automationCreate.emptyTitle')}
        description={t('pages.automationCreate.emptyDescription')}
      />
    </PageContent>
  )
}
