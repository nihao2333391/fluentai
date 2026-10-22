import { useTranslation } from 'react-i18next'

import { EmptyState, PageContent } from '../components/PageState'

export function MyModelsPage() {
  const { t } = useTranslation()
  return (
    <PageContent title={t('pages.myModels.title')} description={t('pages.myModels.description')}>
      <EmptyState
        title={t('pages.myModels.emptyTitle')}
        description={t('pages.myModels.emptyDescription')}
      />
    </PageContent>
  )
}
