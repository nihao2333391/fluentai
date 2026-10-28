import { ApiOutlined, DisconnectOutlined, SaveOutlined } from '@ant-design/icons'
import { App, Button, Card, Form, Input, Select, Space, Tag, Typography } from 'antd'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { FluentConnectionConfig, FluentStatus } from '../../../shared/contracts'
import { fluentAiService } from '../services/fluentAi'
import { useSidecarStore } from '../store/sidecarStore'

interface ConnectionFormValues {
  fluent_connect_mode: 'launch' | 'attach'
  fluent_path: string
  fluent_host: string
  fluent_port: string
}

export function buildFluentConnectionConfig(
  values: Partial<ConnectionFormValues>,
): FluentConnectionConfig {
  const mode = values.fluent_connect_mode ?? 'launch'
  const port = (values.fluent_port ?? '').trim()
  return {
    mode,
    fluent_path: (values.fluent_path ?? '').trim() || null,
    product_version: '25.2.0',
    processor_count: 1,
    ui_mode: 'gui',
    start_timeout: 300,
    cleanup_on_exit: true,
    host: (values.fluent_host ?? '').trim() || '127.0.0.1',
    port: mode === 'attach' && port ? Number.parseInt(port, 10) : null,
  }
}

export function FluentConnectionCard() {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const [form] = Form.useForm<ConnectionFormValues>()
  const connectionMode = Form.useWatch('fluent_connect_mode', form) ?? 'launch'
  const sidecarState = useSidecarStore((state) => state.status.state)
  const [status, setStatus] = useState<FluentStatus | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (sidecarState !== 'ready') {
      return
    }
    let active = true
    void Promise.all([fluentAiService.settings.get(), fluentAiService.fluent.status()]).then(
      ([settings, fluentStatus]) => {
        if (!active) return
        form.setFieldsValue({
          fluent_connect_mode:
            settings.values.fluent_connect_mode === 'attach' ? 'attach' : 'launch',
          fluent_path: settings.values.fluent_path ?? '',
          fluent_host: settings.values.fluent_host ?? '127.0.0.1',
          fluent_port: settings.values.fluent_port ?? '',
        })
        setStatus(fluentStatus)
      },
    )
    return () => {
      active = false
    }
  }, [form, sidecarState])

  const saveConnection = async (): Promise<ConnectionFormValues> => {
    const values = await form.validateFields()
    await fluentAiService.settings.update({
      values: {
        fluent_connect_mode: values.fluent_connect_mode,
        fluent_path: values.fluent_path ?? '',
        fluent_host: values.fluent_host ?? '127.0.0.1',
        fluent_port: values.fluent_port ?? '',
        fluent_ui_mode: 'gui',
        fluent_version: '25.2.0',
      },
    })
    return values
  }

  const save = async (): Promise<void> => {
    setBusy(true)
    try {
      await saveConnection()
      message.success(t('settings.connectionSaved'))
    } catch (error) {
      message.error(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  const connect = async (): Promise<void> => {
    setBusy(true)
    try {
      const values = await saveConnection()
      setStatus(await fluentAiService.fluent.connect(buildFluentConnectionConfig(values)))
    } catch (error) {
      message.error(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  const disconnect = async (): Promise<void> => {
    setBusy(true)
    try {
      setStatus(await fluentAiService.fluent.disconnect())
    } catch (error) {
      message.error(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card
      title={
        <Space>
          {t('settings.fluentConnection')}
          <Tag color={status?.connected ? 'success' : 'default'}>
            {status?.connected ? t('settings.connected') : t('settings.disconnected')}
          </Tag>
        </Space>
      }
    >
      <Form<ConnectionFormValues>
        form={form}
        layout="vertical"
        initialValues={{
          fluent_connect_mode: 'launch',
          fluent_path: '',
          fluent_host: '127.0.0.1',
          fluent_port: '',
        }}
      >
        <Form.Item name="fluent_connect_mode" label={t('settings.connectionMode')}>
          <Select
            options={[
              { value: 'launch', label: t('settings.launch') },
              { value: 'attach', label: t('settings.attach') },
            ]}
          />
        </Form.Item>
        {connectionMode === 'launch' ? (
          <Form.Item
            name="fluent_path"
            label={t('settings.fluentPath')}
            extra={t('settings.fluentPathHelp')}
          >
            <Input
              placeholder={'D:\\Ansys2025R2\\ANSYS Inc\\v252\\fluent\\ntbin\\win64\\fluent.exe'}
            />
          </Form.Item>
        ) : (
          <Space align="start" wrap>
            <Form.Item name="fluent_host" label={t('settings.host')} extra={t('settings.hostHelp')}>
              <Input className="connection-host-input" />
            </Form.Item>
            <Form.Item name="fluent_port" label={t('settings.port')} extra={t('settings.portHelp')}>
              <Input className="connection-port-input" inputMode="numeric" />
            </Form.Item>
          </Space>
        )}
        <Typography.Paragraph type="secondary">
          {connectionMode === 'launch' ? t('settings.launchHelp') : t('settings.attachHelp')}
        </Typography.Paragraph>
      </Form>
      {status?.version ? (
        <Typography.Paragraph type="secondary">
          {status.version}
          {status.pid ? ` · PID ${status.pid}` : ''}
          {status.port ? ` · ${status.host}:${status.port}` : ''}
        </Typography.Paragraph>
      ) : null}
      <Space wrap>
        <Button icon={<SaveOutlined />} loading={busy} onClick={() => void save()}>
          {t('settings.saveConnection')}
        </Button>
        <Button type="primary" icon={<ApiOutlined />} loading={busy} onClick={() => void connect()}>
          {t('common.connect')}
        </Button>
        <Button
          danger
          icon={<DisconnectOutlined />}
          loading={busy}
          disabled={!status?.connected}
          onClick={() => void disconnect()}
        >
          {t('common.disconnect')}
        </Button>
      </Space>
    </Card>
  )
}
