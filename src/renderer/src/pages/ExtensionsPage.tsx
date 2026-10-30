import {
  ArrowRightOutlined,
  BookOutlined,
  CopyOutlined,
  DeploymentUnitOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  InfoCircleOutlined,
  PictureOutlined,
  PlusOutlined,
  ReadOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  SendOutlined,
  SettingOutlined,
  SlidersOutlined,
  ToolOutlined,
} from '@ant-design/icons'
import {
  Alert,
  App,
  Button,
  Card,
  Collapse,
  Descriptions,
  Drawer,
  Dropdown,
  Empty,
  Flex,
  Input,
  Modal,
  Skeleton,
  Spin,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import { ErrorState, LoadingState, PageContent } from '../components/PageState'
import { getFluentAIApi, fluentAiService } from '../services/fluentAi'
import { useSidecarStore } from '../store/sidecarStore'
import type {
  CategoryCapabilities,
  CategoryCapabilityKnowledge,
  CategoryCapabilityTool,
  PartCategory,
} from '../../../shared/contracts'

const CATEGORY_STORAGE_KEY = 'fluent-ai-extension-category'

type CategoriesStatus = 'loading' | 'ready' | 'error'
type CapabilitiesStatus = 'idle' | 'loading' | 'ready' | 'empty' | 'error' | 'unavailable'

type CapabilityResource =
  | { kind: 'knowledge'; item: CategoryCapabilityKnowledge }
  | { kind: 'tool'; item: CategoryCapabilityTool }

type FutureDialogKind = 'upload' | 'image' | 'tool' | 'preferences' | null
type AddGroupKind = 'knowledge' | 'rules' | 'tools'

interface CapabilityGroup {
  key: AddGroupKind
  icon: ReactNode
  label: string
  count: number
}

export function ExtensionsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { modal, message } = App.useApp()
  const sidecarState = useSidecarStore((state) => state.status.state)

  const [categories, setCategories] = useState<PartCategory[]>([])
  const [categoriesStatus, setCategoriesStatus] = useState<CategoriesStatus>('loading')
  const [selectedCategoryId, setSelectedCategoryId] = useState('')
  const [capabilities, setCapabilities] = useState<CategoryCapabilities | null>(null)
  const [capabilitiesStatus, setCapabilitiesStatus] = useState<CapabilitiesStatus>('idle')

  const [composerText, setComposerText] = useState('')
  const [infoDrawerOpen, setInfoDrawerOpen] = useState(false)
  const [selectedResource, setSelectedResource] = useState<CapabilityResource | null>(null)
  const [knowledgePickerOpen, setKnowledgePickerOpen] = useState(false)
  const [addGroup, setAddGroup] = useState<AddGroupKind | null>(null)
  const [futureDialog, setFutureDialog] = useState<FutureDialogKind>(null)

  const capabilitiesRequestRef = useRef(0)

  const selectedCategory = useMemo(
    () => categories.find((category) => category.id === selectedCategoryId) ?? null,
    [categories, selectedCategoryId],
  )

  const loadCategories = () => {
    setCategoriesStatus('loading')
    fluentAiService.categories
      .list()
      .then((list) => {
        setCategories(list)
        setCategoriesStatus('ready')
        setSelectedCategoryId((current) => {
          if (current && list.some((category) => category.id === current)) {
            return current
          }
          const saved = window.localStorage.getItem(CATEGORY_STORAGE_KEY)
          if (saved && list.some((category) => category.id === saved)) {
            return saved
          }
          return list[0]?.id ?? ''
        })
      })
      .catch(() => {
        setCategories([])
        setCategoriesStatus('error')
      })
  }

  useEffect(() => {
    if (sidecarState !== 'ready') {
      return
    }
    loadCategories()
  }, [sidecarState])

  const loadCapabilities = (categoryId: string) => {
    const api = getFluentAIApi()
    if (typeof api.agent?.getCategoryCapabilities !== 'function') {
      setCapabilities(null)
      setCapabilitiesStatus('unavailable')
      return
    }
    const requestId = ++capabilitiesRequestRef.current
    setCapabilities(null)
    setCapabilitiesStatus('loading')
    fluentAiService.agent
      .getCategoryCapabilities(categoryId)
      .then((data) => {
        if (capabilitiesRequestRef.current !== requestId) {
          return
        }
        setCapabilities(data)
        const total = data.knowledge.length + data.rules.length + data.tools.length
        setCapabilitiesStatus(total > 0 ? 'ready' : 'empty')
      })
      .catch(() => {
        if (capabilitiesRequestRef.current !== requestId) {
          return
        }
        setCapabilities(null)
        setCapabilitiesStatus('error')
      })
  }

  useEffect(() => {
    if (!selectedCategoryId || sidecarState !== 'ready') {
      return
    }
    window.localStorage.setItem(CATEGORY_STORAGE_KEY, selectedCategoryId)
    setSelectedResource(null)
    loadCapabilities(selectedCategoryId)
  }, [selectedCategoryId, sidecarState])

  const showNotOpen = () => {
    modal.warning({
      title: t('extensions.notOpenTitle'),
      content: t('extensions.notOpenDesc'),
      okText: t('extensions.gotIt'),
      centered: true,
    })
  }

  const handleSendPreview = () => {
    if (!selectedCategoryId || !composerText.trim()) {
      return
    }
    showNotOpen()
  }

  const handleKnowledgeMenu = () => {
    if (capabilitiesStatus === 'ready' || capabilitiesStatus === 'empty') {
      setKnowledgePickerOpen(true)
      return
    }
    modal.info({
      title: t('extensions.addMenuKnowledge'),
      content:
        capabilitiesStatus === 'unavailable'
          ? t('extensions.knowledgeUnavailable')
          : t('extensions.capabilitiesError'),
      okText: t('extensions.gotIt'),
      centered: true,
    })
  }

  const plusMenuItems = [
    {
      key: 'upload',
      icon: <FileTextOutlined />,
      label: (
        <div>
          <div className="extension-menu-item-title">{t('extensions.addMenuUpload')}</div>
          <div className="extension-menu-item-desc">{t('extensions.addMenuUploadDesc')}</div>
        </div>
      ),
    },
    {
      key: 'image',
      icon: <PictureOutlined />,
      label: (
        <div>
          <div className="extension-menu-item-title">{t('extensions.addMenuImage')}</div>
          <div className="extension-menu-item-desc">{t('extensions.addMenuImageDesc')}</div>
        </div>
      ),
    },
    {
      key: 'knowledge',
      icon: <BookOutlined />,
      label: (
        <div>
          <div className="extension-menu-item-title">{t('extensions.addMenuKnowledge')}</div>
          <div className="extension-menu-item-desc">{t('extensions.addMenuKnowledgeDesc')}</div>
        </div>
      ),
    },
    {
      key: 'tool',
      icon: <ToolOutlined />,
      label: (
        <div>
          <div className="extension-menu-item-title">
            {t('extensions.addMenuTool')}
            <Tag className="extension-menu-tag">{t('extensions.futureTag')}</Tag>
          </div>
          <div className="extension-menu-item-desc">{t('extensions.addMenuToolDesc')}</div>
        </div>
      ),
    },
  ]

  const handlePlusMenuClick = ({ key }: { key: string }) => {
    if (key === 'knowledge') {
      handleKnowledgeMenu()
      return
    }
    setFutureDialog(key as Exclude<FutureDialogKind, null>)
  }

  const targetChipItems = categories.map((category) => ({
    key: category.id,
    label: category.name || category.id,
  }))

  const copyCategoryId = async (categoryId: string) => {
    try {
      await navigator.clipboard.writeText(categoryId)
    } catch {
      const textarea = document.createElement('textarea')
      textarea.value = categoryId
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      textarea.remove()
    }
    message.success(t('extensions.infoIdCopied'))
  }

  const flowSteps = [
    {
      icon: <FileTextOutlined />,
      title: t('extensions.flowStep1Title'),
      desc: t('extensions.flowStep1Desc'),
    },
    {
      icon: <ExperimentOutlined />,
      title: t('extensions.flowStep2Title'),
      desc: t('extensions.flowStep2Desc'),
    },
    {
      icon: <DeploymentUnitOutlined />,
      title: t('extensions.flowStep3Title'),
      desc: t('extensions.flowStep3Desc'),
    },
  ]

  const capabilityGroups: CapabilityGroup[] = [
    {
      key: 'knowledge',
      icon: <ReadOutlined />,
      label: t('extensions.knowledgeGroup'),
      count: capabilities?.knowledge.length ?? 0,
    },
    {
      key: 'rules',
      icon: <SafetyCertificateOutlined />,
      label: t('extensions.rulesGroup'),
      count: capabilities?.rules.length ?? 0,
    },
    {
      key: 'tools',
      icon: <ToolOutlined />,
      label: t('extensions.toolsGroup'),
      count: capabilities?.tools.length ?? 0,
    },
  ]

  const renderGroupContent = (groupKey: AddGroupKind) => {
    if (!capabilities) {
      return null
    }
    if (groupKey === 'knowledge') {
      if (capabilities.knowledge.length === 0) {
        return <Typography.Text type="secondary">{t('extensions.groupEmpty')}</Typography.Text>
      }
      return (
        <div className="extension-resource-list">
          {capabilities.knowledge.map((item) => (
            <button
              type="button"
              key={item.id}
              className="extension-resource-row"
              onClick={() => setSelectedResource({ kind: 'knowledge', item })}
            >
              <BookOutlined />
              <span className="extension-resource-title">{item.name}</span>
              <Tag color={item.status === 'enabled' ? 'success' : 'default'}>
                {item.status === 'enabled'
                  ? t('extensions.statusEnabled')
                  : t('extensions.statusDisabled')}
              </Tag>
            </button>
          ))}
        </div>
      )
    }
    if (groupKey === 'tools') {
      if (capabilities.tools.length === 0) {
        return <Typography.Text type="secondary">{t('extensions.groupEmpty')}</Typography.Text>
      }
      return (
        <div className="extension-resource-list">
          {capabilities.tools.map((item) => (
            <button
              type="button"
              key={item.name}
              className="extension-resource-row"
              onClick={() => setSelectedResource({ kind: 'tool', item })}
            >
              <ToolOutlined />
              <span className="extension-resource-title">
                {item.display_name || item.name}
              </span>
              <Tag color={item.status === 'enabled' ? 'success' : 'default'}>
                {item.status === 'enabled'
                  ? t('extensions.statusEnabled')
                  : t('extensions.statusDisabled')}
              </Tag>
            </button>
          ))}
        </div>
      )
    }
    return <Typography.Text type="secondary">{t('extensions.groupEmpty')}</Typography.Text>
  }

  const configuredCount = capabilities
    ? capabilities.knowledge.length + capabilities.rules.length + capabilities.tools.length
    : 0

  const previewBadge = (
    <Tooltip title={t('extensions.previewTooltip')}>
      <Tag icon={<InfoCircleOutlined />} className="extension-preview-badge">
        {t('extensions.previewBadge')}
      </Tag>
    </Tooltip>
  )

  const renderBody = () => {
    if (categoriesStatus === 'loading') {
      return <LoadingState />
    }
    if (categoriesStatus === 'error') {
      return (
        <ErrorState
          title={t('extensions.categoriesError')}
          description={t('extensions.categoriesError')}
          onRetry={loadCategories}
          retryLabel={t('common.reload')}
        />
      )
    }
    if (categories.length === 0) {
      return (
        <div className="page-state-card">
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <div>
                <Typography.Text strong>{t('extensions.noCategoriesTitle')}</Typography.Text>
                <Typography.Paragraph type="secondary" className="state-description">
                  {t('extensions.noCategoriesDesc')}
                </Typography.Paragraph>
              </div>
            }
          />
          <Button type="primary" onClick={() => navigate('/meshing')}>
            {t('extensions.goTemplateLibrary')}
          </Button>
        </div>
      )
    }
    return (
      <>
        <div className="extension-target-bar">
          <div className="extension-target-left">
            <Typography.Text type="secondary">{t('extensions.targetCategory')}</Typography.Text>
            <select
              className="extension-category-select"
              value={selectedCategoryId}
              onChange={(event) => setSelectedCategoryId(event.target.value)}
              aria-label={t('extensions.targetCategory')}
            >
              {!selectedCategoryId ? (
                <option value="">{t('extensions.selectCategoryPlaceholder')}</option>
              ) : null}
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name || category.id}
                </option>
              ))}
            </select>
            <Typography.Text type="secondary" className="extension-share-note">
              {t('extensions.shareNote')}
            </Typography.Text>
          </div>
          <Button icon={<SettingOutlined />} onClick={() => setInfoDrawerOpen(true)}>
            {t('extensions.repoInfo')}
          </Button>
        </div>

        <div className="extension-columns">
          <Card className="extension-builder-card" variant="outlined">
            <div className="extension-builder-header">
              <div className="extension-builder-avatar">
                <RobotOutlined />
              </div>
              <div className="extension-builder-titles">
                <Flex align="center" gap={8} wrap>
                  <Typography.Text strong className="extension-builder-title">
                    {t('extensions.builderTitle')}
                  </Typography.Text>
                  <Tag>{t('extensions.futureTag')}</Tag>
                </Flex>
                <Typography.Text type="secondary">{t('extensions.builderDesc')}</Typography.Text>
              </div>
            </div>

            <div className="extension-conversation">
              <div className="extension-demo-label">
                <Tag>{t('extensions.demoLabel')}</Tag>
              </div>
              <div className="extension-bubble extension-bubble-user">
                {t('extensions.demoUserMessage')}
              </div>
              <div className="extension-bubble extension-bubble-ai">
                <RobotOutlined className="extension-bubble-ai-icon" />
                <span>{t('extensions.demoAiMessage')}</span>
              </div>
              <div className="extension-flow">
                {flowSteps.map((step, index) => (
                  <div className="extension-flow-step" key={step.title}>
                    <div className="extension-flow-icon">{step.icon}</div>
                    <div className="extension-flow-text">
                      <Typography.Text strong>{step.title}</Typography.Text>
                      <Typography.Paragraph type="secondary" className="extension-flow-desc">
                        {step.desc}
                      </Typography.Paragraph>
                    </div>
                    {index < flowSteps.length - 1 ? (
                      <ArrowRightOutlined className="extension-flow-arrow" />
                    ) : null}
                  </div>
                ))}
              </div>
            </div>

            <div className="extension-composer">
              <Dropdown
                trigger={['click']}
                menu={{ items: plusMenuItems, onClick: handlePlusMenuClick }}
              >
                <Button
                  type="text"
                  shape="circle"
                  icon={<PlusOutlined />}
                  aria-label={t('extensions.addMenuUpload')}
                />
              </Dropdown>
              <Input.TextArea
                value={composerText}
                onChange={(event) => setComposerText(event.target.value)}
                onPressEnter={(event) => {
                  if (!event.shiftKey) {
                    event.preventDefault()
                    handleSendPreview()
                  }
                }}
                autoSize={{ minRows: 1, maxRows: 5 }}
                placeholder={t('extensions.composerPlaceholder')}
              />
              <Dropdown
                trigger={['click']}
                menu={{
                  items: targetChipItems,
                  selectedKeys: selectedCategoryId ? [selectedCategoryId] : [],
                  onClick: ({ key }) => setSelectedCategoryId(key),
                }}
              >
                <Button className="extension-target-chip">
                  {t('extensions.targetChip')}：{selectedCategory?.name ?? t('extensions.noTarget')}
                </Button>
              </Dropdown>
              <Tooltip title={t('extensions.preferences')}>
                <Button
                  type="text"
                  shape="circle"
                  icon={<SlidersOutlined />}
                  aria-label={t('extensions.preferences')}
                  onClick={() => setFutureDialog('preferences')}
                />
              </Tooltip>
              <Tooltip title={t('extensions.sendTooltip')}>
                <Button
                  type="primary"
                  shape="circle"
                  icon={<SendOutlined />}
                  disabled={!selectedCategoryId || !composerText.trim()}
                  aria-label={t('extensions.sendTooltip')}
                  onClick={handleSendPreview}
                />
              </Tooltip>
            </div>
          </Card>

          <aside className="extension-capability-panel">
            <Card
              variant="outlined"
              className="extension-capability-card"
              title={
                <Flex align="center" gap={8} wrap>
                  <span>{t('extensions.panelTitle')}</span>
                  {selectedCategory ? (
                    <Typography.Text type="secondary" className="extension-panel-category">
                      {selectedCategory.name}
                    </Typography.Text>
                  ) : null}
                  {capabilitiesStatus === 'ready' ? (
                    <Tag color="blue">
                      {t('extensions.configuredCount', { count: configuredCount })}
                    </Tag>
                  ) : null}
                </Flex>
              }
            >
              {capabilitiesStatus === 'loading' || capabilitiesStatus === 'idle' ? (
                <div className="extension-panel-state">
                  <Spin size="small" />
                  <Typography.Text type="secondary">
                    {t('extensions.capabilitiesLoading')}
                  </Typography.Text>
                </div>
              ) : null}

              {capabilitiesStatus === 'error' ? (
                <div className="extension-panel-state">
                  <Typography.Text type="warning">
                    {t('extensions.capabilitiesError')}
                  </Typography.Text>
                  <Button size="small" onClick={() => loadCapabilities(selectedCategoryId)}>
                    {t('common.reload')}
                  </Button>
                </div>
              ) : null}

              {capabilitiesStatus === 'unavailable' ? (
                <div className="extension-panel-state">
                  <Typography.Text type="secondary">
                    {t('extensions.capabilitiesUnavailable')}
                  </Typography.Text>
                </div>
              ) : null}

              {capabilitiesStatus === 'empty' ? (
                <div className="extension-panel-state">
                  <Typography.Text type="secondary">
                    {t('extensions.capabilitiesEmpty')}
                  </Typography.Text>
                </div>
              ) : null}

              {capabilitiesStatus === 'ready' && capabilities ? (
                <>
                  <Collapse
                    ghost
                    defaultActiveKey={['knowledge', 'rules', 'tools']}
                    items={capabilityGroups.map((group) => ({
                      key: group.key,
                      label: (
                        <Flex align="center" gap={8}>
                          {group.icon}
                          <span>{group.label}</span>
                          <Tag>{group.count}</Tag>
                        </Flex>
                      ),
                      extra: (
                        <Button
                          type="text"
                          size="small"
                          shape="circle"
                          icon={<PlusOutlined />}
                          aria-label={t('extensions.addCapabilityTitle')}
                          onClick={(event) => {
                            event.stopPropagation()
                            setAddGroup(group.key)
                          }}
                        />
                      ),
                      children: renderGroupContent(group.key),
                    }))}
                  />
                  <Alert
                    type="info"
                    showIcon
                    message={t('extensions.manageNoteTitle')}
                    description={t('extensions.manageNoteDesc')}
                    className="extension-manage-note"
                  />
                </>
              ) : null}
            </Card>
          </aside>
        </div>
      </>
    )
  }

  const groupTypeKey =
    addGroup === 'knowledge'
      ? 'extensions.typeKnowledge'
      : addGroup === 'rules'
        ? 'extensions.typeRule'
        : 'extensions.typeTool'

  const futureDialogContent: Record<Exclude<FutureDialogKind, null>, { titleKey: string; descKey: string }> =
    {
      upload: {
        titleKey: 'extensions.uploadFutureTitle',
        descKey: 'extensions.uploadFutureDesc',
      },
      image: {
        titleKey: 'extensions.imageFutureTitle',
        descKey: 'extensions.imageFutureDesc',
      },
      tool: {
        titleKey: 'extensions.toolFutureTitle',
        descKey: 'extensions.toolFutureDesc',
      },
      preferences: {
        titleKey: 'extensions.preferencesTitle',
        descKey: 'extensions.preferencesDesc',
      },
    }

  return (
    <PageContent
      title={t('extensions.title')}
      description={t('extensions.subtitle')}
      actions={previewBadge}
    >
      {renderBody()}

      {(['upload', 'image', 'tool', 'preferences'] as const).map((kind) => (
        <Modal
          key={kind}
          open={futureDialog === kind}
          title={t(futureDialogContent[kind].titleKey)}
          footer={
            <Button type="primary" onClick={() => setFutureDialog(null)}>
              {t('extensions.gotIt')}
            </Button>
          }
          onCancel={() => setFutureDialog(null)}
          centered
        >
          <Typography.Paragraph>{t(futureDialogContent[kind].descKey)}</Typography.Paragraph>
        </Modal>
      ))}

      <Modal
        open={addGroup !== null}
        title={t('extensions.addCapabilityTitle')}
        footer={
          <Button type="primary" onClick={() => setAddGroup(null)}>
            {t('extensions.gotIt')}
          </Button>
        }
        onCancel={() => setAddGroup(null)}
        centered
      >
        <Typography.Paragraph>
          {addGroup ? t('extensions.addCapabilityDesc', { type: t(groupTypeKey) }) : null}
        </Typography.Paragraph>
      </Modal>

      <Modal
        open={knowledgePickerOpen}
        title={t('extensions.knowledgePickTitle')}
        footer={
          <Button onClick={() => setKnowledgePickerOpen(false)}>{t('extensions.close')}</Button>
        }
        onCancel={() => setKnowledgePickerOpen(false)}
        centered
      >
        <Typography.Paragraph type="secondary">
          {t('extensions.knowledgePickDesc')}
        </Typography.Paragraph>
        {!capabilities || capabilities.knowledge.length === 0 ? (
          <Typography.Text type="secondary">{t('extensions.knowledgeEmpty')}</Typography.Text>
        ) : (
          <div className="extension-resource-list">
            {capabilities.knowledge.map((item) => (
              <button
                type="button"
                key={item.id}
                className="extension-resource-row"
                onClick={() => setSelectedResource({ kind: 'knowledge', item })}
              >
                <BookOutlined />
                <span className="extension-resource-title">{item.name}</span>
                <Tag color={item.status === 'enabled' ? 'success' : 'default'}>
                  {item.status === 'enabled'
                    ? t('extensions.statusEnabled')
                    : t('extensions.statusDisabled')}
                </Tag>
              </button>
            ))}
          </div>
        )}
      </Modal>

      <Drawer
        open={infoDrawerOpen}
        width={440}
        title={t('extensions.drawerInfoTitle')}
        onClose={() => setInfoDrawerOpen(false)}
        extra={
          <Button size="small" onClick={() => navigate('/meshing')}>
            {t('extensions.viewInLibrary')}
          </Button>
        }
      >
        {selectedCategory ? (
          <>
            <Typography.Title level={5} className="extension-drawer-subtitle">
              {selectedCategory.name || selectedCategory.id}
            </Typography.Title>
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label={t('extensions.infoName')}>
                {selectedCategory.name || selectedCategory.id}
              </Descriptions.Item>
              <Descriptions.Item label={t('extensions.infoId')}>
                <Flex align="center" gap={8} wrap>
                  <Typography.Text className="extension-mono">{selectedCategory.id}</Typography.Text>
                  <Button
                    type="text"
                    size="small"
                    icon={<CopyOutlined />}
                    aria-label={t('extensions.infoId')}
                    onClick={() => void copyCategoryId(selectedCategory.id)}
                  />
                </Flex>
              </Descriptions.Item>
              <Descriptions.Item label={t('extensions.infoDescription')}>
                {selectedCategory.description?.trim()
                  ? selectedCategory.description
                  : t('extensions.notProvided')}
              </Descriptions.Item>
              <Descriptions.Item label={t('extensions.infoCapabilities')}>
                {capabilities
                  ? t('extensions.capabilityUnit', {
                      knowledge: capabilities.knowledge.length,
                      rules: capabilities.rules.length,
                      tools: capabilities.tools.length,
                    })
                  : t('extensions.capabilitiesLoading')}
              </Descriptions.Item>
              <Descriptions.Item label={t('extensions.infoInheritTitle')}>
                {t('extensions.infoInheritDesc')}
              </Descriptions.Item>
            </Descriptions>
            <Typography.Paragraph type="secondary" className="extension-drawer-note">
              {t('extensions.infoFooter')}
            </Typography.Paragraph>
          </>
        ) : (
          <Skeleton active paragraph={{ rows: 3 }} />
        )}
      </Drawer>

      <Drawer
        open={selectedResource !== null}
        width={440}
        onClose={() => setSelectedResource(null)}
        title={
          selectedResource
            ? selectedResource.kind === 'knowledge'
              ? selectedResource.item.name
              : selectedResource.item.display_name || selectedResource.item.name
            : ''
        }
      >
        {selectedResource ? (
          <>
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label={t('extensions.detailType')}>
                {selectedResource.kind === 'knowledge'
                  ? t('extensions.typeKnowledge')
                  : t('extensions.typeTool')}
              </Descriptions.Item>
              <Descriptions.Item label={t('extensions.detailStatus')}>
                <Tag color={selectedResource.item.status === 'enabled' ? 'success' : 'default'}>
                  {selectedResource.item.status === 'enabled'
                    ? t('extensions.statusEnabled')
                    : t('extensions.statusDisabled')}
                </Tag>
              </Descriptions.Item>
              {selectedResource.kind === 'tool' ? (
                <Descriptions.Item label={t('extensions.detailSource')}>
                  {selectedResource.item.source || t('extensions.notProvided')}
                </Descriptions.Item>
              ) : (
                <Descriptions.Item label={t('extensions.detailFiles')}>
                  {selectedResource.item.files.length > 0 ? (
                    <Flex vertical gap={4}>
                      {selectedResource.item.files.map((file) => (
                        <Typography.Text key={file} className="extension-mono">
                          {file}
                        </Typography.Text>
                      ))}
                    </Flex>
                  ) : (
                    t('extensions.notProvided')
                  )}
                </Descriptions.Item>
              )}
              <Descriptions.Item label={t('extensions.detailCategory')}>
                {selectedCategory?.name ?? selectedCategoryId}
              </Descriptions.Item>
            </Descriptions>
            <Button
              type="primary"
              block
              className="extension-drawer-close"
              onClick={() => setSelectedResource(null)}
            >
              {t('extensions.close')}
            </Button>
          </>
        ) : null}
      </Drawer>
    </PageContent>
  )
}
