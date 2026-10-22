import { useTranslation } from 'react-i18next'

import { EmptyState, PageContent } from '../components/PageState'

export function MyAutomationsPage() {
  const { t } = useTranslation()
  return (
    <PageContent
      title={t('pages.myAutomations.title')}
      description={t('pages.myAutomations.description')}
    >
      <EmptyState
        title={t('pages.myAutomations.emptyTitle')}
        description={t('pages.myAutomations.emptyDescription')}
      />
    </PageContent>
  )
}
