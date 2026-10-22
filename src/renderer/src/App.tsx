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

export default function App() {
  const platform = window.fluentAI?.platform ?? 'browser'

  return (
    <main className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">FLUENT AI</p>
          <h1>桌面应用基础框架已就绪</h1>
          <p className="summary">
            Electron、React 与 FastAPI 侧车的基础工程已经建立。当前页面仅用于验证 M1
            开发环境，不包含业务功能。
          </p>
        </div>
        <span className="status">M1 Foundation</span>
      </header>

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
        <span>下一阶段：接口契约与侧车通信</span>
      </footer>
    </main>
  )
}
