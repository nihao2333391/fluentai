import { useEffect, useState } from 'react'

const QUERY = '(prefers-color-scheme: dark)'

export function useSystemDark(): boolean {
  const [isDark, setIsDark] = useState(() => window.matchMedia?.(QUERY).matches ?? false)

  useEffect(() => {
    const media = window.matchMedia?.(QUERY)
    if (!media) {
      return
    }
    const onChange = (event: MediaQueryListEvent): void => {
      setIsDark(event.matches)
    }
    media.addEventListener('change', onChange)
    return () => {
      media.removeEventListener('change', onChange)
    }
  }, [])

  return isDark
}
