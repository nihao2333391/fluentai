import {
  ApiOutlined,
  DisconnectOutlined,
  ExperimentOutlined,
  SaveOutlined,
} from '@ant-design/icons'
import {
  Alert,
  App,
  Button,
  Card,
  Divider,
  Form,
  Input,
  List,
  Select,
  Space,
  Tag,
  Typography,
} from 'antd'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import type {
  FluentConnectionConfig,
  FluentStatus,
  MeshingArgumentReference,
  MeshingReadReport,
  MeshingWorkflowType,
  MeshingWriteReport,
} from '../../../shared/contracts'
import { fluentAiService } from '../services/fluentAi'
import { useSidecarStore } from '../store/sidecarStore'

interface MeshingConnectionFormValues {
  meshing_connect_mode: 'launch' | 'attach'
  meshing_fluent_path: string
  meshing_host: string
  meshing_port: string
  meshing_ui_mode: 'no_gui' | 'gui'
}

const DIAGNOSTIC_FIELDS: Record<MeshingWorkflowType, MeshingArgumentReference[]> = {
  watertight: [
    { task_path: ['import_geometry'], argument_path: ['file_format'] },
    { task_path: ['import_geometry'], argument_path: ['import_type'] },
    { task_path: ['import_geometry'], argument_path: ['length_unit'] },
    {
      task_path: ['create_surface_mesh'],
      argument_path: ['cfd_surface_mesh_controls', 'min_size'],
    },
    {
      task_path: ['create_surface_mesh'],
      argument_path: ['cfd_surface_mesh_controls', 'max_size'],
    },
    { task_path: ['create_volume_mesh'], argument_path: ['volume_fill'] },
  ],
  'fault-tolerant': [
    {
      task_path: ['import_cad_and_part_management'],
      argument_path: ['file_loaded'],
    },
    { task_path: ['mesh_controls_table'], argument_path: ['global_max'] },
    { task_path: ['mesh_controls_table'], argument_path: ['target_growth_rate'] },
  ],
}

export function MeshingConnectionCard() {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const [form] = Form.useForm<MeshingConnectionFormValues>()
  const sidecarState = useSidecarStore((state) => state.status.state)
  const [status, setStatus] = useState<FluentStatus | null>(null)
  const [workflowType, setWorkflowType] = useState<MeshingWorkflowType>('watertight')
  const [busy, setBusy] = useState(false)
  const [readReport, setReadReport] = useState<MeshingReadReport | null>(null)
  const [writeReport, setWriteReport] = useState<MeshingWriteReport | null>(null)

  useEffect(() => {
    if (sidecarState !== 'ready') return
    let active = true
    void Promise.all([fluentAiService.settings.get(), fluentAiService.meshing.status()]).then(
      ([settings, meshingStatus]) => {
        if (!active) return
        form.setFieldsValue({
          meshing_connect_mode:
            settings.values.meshing_connect_mode === 'attach' ? 'attach' : 'launch',
          meshing_fluent_path:
            settings.values.meshing_fluent_path ?? settings.values.fluent_path ?? '',
          meshing_host: settings.values.meshing_host ?? '127.0.0.1',
          meshing_port: settings.values.meshing_port ?? '',
          meshing_ui_mode: settings.values.meshing_ui_mode === 'gui' ? 'gui' : 'no_gui',
        })
        setStatus(meshingStatus)
      },
    )
    return () => {
      active = false
    }
  }, [form, sidecarState])

  const saveConnection = async (): Promise<MeshingConnectionFormValues> => {
    const values = await form.validateFields()
    await fluentAiService.settings.update({
      values: {
        meshing_connect_mode: values.meshing_connect_mode,
        meshing_fluent_path: values.meshing_fluent_path ?? '',
        meshing_host: values.meshing_host ?? '127.0.0.1',
        meshing_port: values.meshing_port ?? '',
        meshing_ui_mode: values.meshing_ui_mode,
      },
    })
    return values
  }

  const connect = async (): Promise<void> => {
    setBusy(true)
    setReadReport(null)
    setWriteReport(null)
    try {
      const values = await saveConnection()
      const port = values.meshing_port.trim()
      const config: FluentConnectionConfig = {
        mode: values.meshing_connect_mode,
        fluent_path: values.meshing_fluent_path.trim() || null,
        product_version: '25.2.0',
        processor_count: 1,
        ui_mode: values.meshing_ui_mode,
        start_timeout: 300,
        cleanup_on_exit: true,
        host: values.meshing_host.trim() || '127.0.0.1',
        port: port ? Number.parseInt(port, 10) : null,
      }
      setStatus(await fluentAiService.meshing.connect(config))
    } catch (error) {
      message.error(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  const disconnect = async (): Promise<void> => {
    setBusy(true)
    try {
      setStatus(await fluentAiService.meshing.disconnect())
      setReadReport(null)
      setWriteReport(null)
    } catch (error) {
      message.error(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  const diagnose = async (): Promise<void> => {
    if (!status?.connected) {
      message.warning(t('settings.meshingNotConnected'))
      return
    }
    setBusy(true)
    setReadReport(null)
    setWriteReport(null)
    try {
      const read = await fluentAiService.meshing.read({
        workflow_type: workflowType,
        items: DIAGNOSTIC_FIELDS[workflowType],
      })
      setReadReport(read)
      if (read.status !== 'success') {
        throw new Error(read.error ?? t('settings.meshingDiagnosticFailed'))
      }
      const sample = read.items.find(
        (item) => item.found && item.value !== null && item.value !== undefined,
      )
      if (!sample) {
        throw new Error(read.error ?? t('settings.meshingDiagnosticFailed'))
      }
      const write = await fluentAiService.meshing.write({
        workflow_type: workflowType,
        verify: true,
        items: [
          {
            task_path: sample.task_path,
            argument_path: sample.argument_path,
            compound_child_name: sample.compound_child_name ?? null,
            value: sample.value,
            required: true,
          },
        ],
      })
      setWriteReport(write)
      if (write.status !== 'success') {
        throw new Error(write.error ?? t('settings.meshingDiagnosticFailed'))
      }
      message.success(t('settings.meshingDiagnosticSuccess'))
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
          {t('settings.meshingConnection')}
          <Tag color={status?.connected ? 'success' : 'default'}>
            {status?.connected ? t('settings.connected') : t('settings.disconnected')}
          </Tag>
        </Space>
      }
    >
      <Form<MeshingConnectionFormValues>
        form={form}
        layout="vertical"
        initialValues={{
          meshing_connect_mode: 'launch',
          meshing_fluent_path: '',
          meshing_host: '127.0.0.1',
          meshing_port: '',
          meshing_ui_mode: 'no_gui',
        }}
      >
        <Space align="start" wrap>
          <Form.Item name="meshing_connect_mode" label={t('settings.connectionMode')}>
            <Select
              options={[
                { value: 'launch', label: t('settings.launch') },
                { value: 'attach', label: t('settings.attach') },
              ]}
            />
          </Form.Item>
          <Form.Item name="meshing_ui_mode" label={t('settings.meshingUiMode')}>
            <Select
              options={[
                { value: 'no_gui', label: t('settings.meshingBackground') },
                { value: 'gui', label: t('settings.meshingGui') },
              ]}
            />
          </Form.Item>
        </Space>
        <Form.Item name="meshing_fluent_path" label={t('settings.fluentPath')}>
          <Input
            placeholder={'D:\\Ansys2025R2\\ANSYS Inc\\v252\\fluent\\ntbin\\win64\\fluent.exe'}
          />
        </Form.Item>
        <Space align="start" wrap>
          <Form.Item name="meshing_host" label={t('settings.host')}>
            <Input className="connection-host-input" />
          </Form.Item>
          <Form.Item name="meshing_port" label={t('settings.port')}>
            <Input className="connection-port-input" inputMode="numeric" />
          </Form.Item>
        </Space>
      </Form>
      {status?.version ? (
        <Typography.Paragraph type="secondary">
          {status.version}
          {status.pid ? ` · PID ${status.pid}` : ''}
          {status.port ? ` · ${status.host}:${status.port}` : ''}
        </Typography.Paragraph>
      ) : null}
      {status?.mode === 'attach' ? (
        <Alert
          type="warning"
          showIcon
          message={t('settings.meshingAttachLimited')}
          className="full-width"
        />
      ) : null}
      <Space wrap>
        <Button icon={<SaveOutlined />} loading={busy} onClick={() => void saveConnection()}>
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

      <Divider />
      <Space direction="vertical" size={12} className="full-width">
        <Space wrap>
          <Typography.Text strong>{t('settings.meshingWorkflow')}</Typography.Text>
          <Select<MeshingWorkflowType>
            value={workflowType}
            onChange={(value) => {
              setWorkflowType(value)
              setReadReport(null)
              setWriteReport(null)
            }}
            options={[
              { value: 'watertight', label: t('meshing.watertight') },
              { value: 'fault-tolerant', label: t('meshing.faultTolerant') },
            ]}
          />
          <Button
            icon={<ExperimentOutlined />}
            loading={busy}
            disabled={!status?.connected}
            onClick={() => void diagnose()}
          >
            {busy ? t('settings.meshingDiagnosticRunning') : t('settings.meshingDiagnostic')}
          </Button>
        </Space>
        {readReport ? (
          <Alert
            type={readReport.status === 'success' ? 'success' : 'error'}
            showIcon
            message={t('settings.meshingTaskCount', { count: readReport.task_names.length })}
            description={
              <Space direction="vertical" size={6} className="full-width">
                <span>{t('settings.meshingReadCount', { count: readReport.items.length })}</span>
                {writeReport ? (
                  <span>
                    {t('settings.meshingWriteVerified', {
                      count: writeReport.results.filter((result) => result.success).length,
                    })}
                  </span>
                ) : null}
                <List
                  size="small"
                  dataSource={readReport.items}
                  renderItem={(item) => (
                    <List.Item>
                      <Space direction="vertical" size={0}>
                        <Typography.Text code>
                          {item.task_path.join('.')} / {item.argument_path.join('.')}
                        </Typography.Text>
                        <Typography.Text type="secondary">
                          {JSON.stringify(item.value)}
                        </Typography.Text>
                      </Space>
                    </List.Item>
                  )}
                />
              </Space>
            }
          />
        ) : null}
      </Space>
    </Card>
  )
}
