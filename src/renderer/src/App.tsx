import { useEffect, useState } from 'react'

import type { CredentialStatus, SidecarStatus } from '../../shared/contracts'
import { fluentAiService } from './services/fluentAi'

const modules = [
  {
    name: '自动化创建',
    description: '定义可复用的 Fluent 设置预设',
  },
  {
    name: '我的自动化',
    description: '应用、编辑和同步自动化',
  },
  {
    name: '我的模型',
    description: '管理算例并关联自动化',
  },
  {
    name: '设置',
    description: '配置 Fluent 连接与应用偏好',
  },
]

const statusLabels: Record<SidecarStatus['state'], string> = {
  stopped: '未启动',
  starting: '启动中',
  ready: '已就绪',
  restarting: '重启中',
  error: '异常',
}

const initialStatus: SidecarStatus = {
  state: 'starting',
  message: '正在连接 Electron preload API...',
}

export default function App() {
  const [sidecarStatus, setSidecarStatus] = useState<SidecarStatus>(() =>
    window.fluentAI?.sidecar
      ? initialStatus
      : {
          state: 'error',
          message: 'Electron preload API is unavailable.',
        },
  )
  const [restarting, setRestarting] = useState(false)
  const [credentialStatus, setCredentialStatus] = useState<CredentialStatus | null>(null)
  const platform = window.fluentAI?.platform ?? 'browser'

  useEffect(() => {
    const sidecar = window.fluentAI?.sidecar
    if (!sidecar) {
      return
    }

    let active = true
    void sidecar.getStatus().then((status) => {
      if (active) {
        setSidecarStatus(status)
      }
    })

    const unsubscribe = sidecar.onStatusChanged((status) => {
      if (active) {
        setSidecarStatus(status)
      }
    })

    return () => {
      active = false
      unsubscribe()
    }
  }, [])

  useEffect(() => {
    if (!window.fluentAI) {
      return
    }
    let active = true
    void fluentAiService.credentials
      .getStatus()
      .then((status) => {
        if (active) {
          setCredentialStatus(status)
        }
      })
      .catch(() => {
        if (active) {
          setCredentialStatus({ encryptionAvailable: false, configured: false })
        }
      })
    return () => {
      active = false
    }
  }, [])

  const restartSidecar = async (): Promise<void> => {
    const sidecar = window.fluentAI?.sidecar
    if (!sidecar || restarting) {
      return
    }

    setRestarting(true)
    try {
      setSidecarStatus(await sidecar.restart())
    } catch (error) {
      setSidecarStatus({
        state: 'error',
        message: error instanceof Error ? error.message : String(error),
      })
    } finally {
      setRestarting(false)
    }
  }

  return (
    <main className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">FLUENT AI</p>
          <h1>桌面应用安全基础已就绪</h1>
          <p className="summary">
            Electron、React 与 FastAPI 侧车已经联通。M4 增加了安全文件选择、加密凭据存储、 业务 IPC
            和类型化 Renderer 服务层；完整业务页面将在后续阶段实现。
          </p>
        </div>
        <span className={`status status--${sidecarStatus.state}`}>
          Sidecar {statusLabels[sidecarStatus.state]}
        </span>
      </header>

      <section className="sidecar-panel" aria-label="FastAPI 侧车状态">
        <div>
          <p className="panel-label">LOCAL FASTAPI SIDECAR</p>
          <h2>{statusLabels[sidecarStatus.state]}</h2>
          <p className="panel-message">{sidecarStatus.message ?? '等待状态更新...'}</p>
          <div className="sidecar-meta">
            {sidecarStatus.version ? <span>版本 {sidecarStatus.version}</span> : null}
            {sidecarStatus.pid ? <span>PID {sidecarStatus.pid}</span> : null}
            {sidecarStatus.port ? <span>127.0.0.1:{sidecarStatus.port}</span> : null}
            {credentialStatus ? (
              <span>
                凭据存储：{credentialStatus.encryptionAvailable ? '可用' : '不可用'}
                {credentialStatus.configured ? ' / 已配置' : ''}
              </span>
            ) : null}
          </div>
        </div>
        <button
          type="button"
          className="restart-button"
          disabled={restarting || sidecarStatus.state === 'starting'}
          onClick={() => void restartSidecar()}
        >
          {restarting ? '正在重启...' : '重启侧车'}
        </button>
      </section>

      <section className="module-grid" aria-label="计划中的一级模块">
        {modules.map((module) => (
          <article className="module-card" key={module.name}>
            <h2>{module.name}</h2>
            <p>{module.description}</p>
            <span>计划中</span>
          </article>
        ))}
      </section>

      <footer>
        <span>运行平台：{platform}</span>
        <span>下一阶段：界面框架与设计系统</span>
      </footer>
    </main>
  )
}
