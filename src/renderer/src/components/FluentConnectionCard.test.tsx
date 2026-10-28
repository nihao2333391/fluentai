import { describe, expect, it } from 'vitest'

import { buildFluentConnectionConfig } from './FluentConnectionCard'

describe('FluentConnectionCard connection config', () => {
  it('handles fields omitted when launch mode unmounts the attach inputs', () => {
    expect(
      buildFluentConnectionConfig({
        fluent_connect_mode: 'launch',
        fluent_path: 'D:\\Ansys\\fluent.exe',
      }),
    ).toMatchObject({
      mode: 'launch',
      fluent_path: 'D:\\Ansys\\fluent.exe',
      host: '127.0.0.1',
      port: null,
    })
  })

  it('uses the host and port when connecting to an existing session', () => {
    expect(
      buildFluentConnectionConfig({
        fluent_connect_mode: 'attach',
        fluent_host: ' 192.168.1.8 ',
        fluent_port: ' 51000 ',
      }),
    ).toMatchObject({ mode: 'attach', fluent_path: null, host: '192.168.1.8', port: 51000 })
  })
})
