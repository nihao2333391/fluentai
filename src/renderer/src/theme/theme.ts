import { theme, type ThemeConfig } from 'antd'

export const getThemeConfig = (isDark: boolean): ThemeConfig => ({
  algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
  token: {
    colorPrimary: '#1677ff',
    colorInfo: '#1677ff',
    colorSuccess: '#16a34a',
    colorWarning: '#d97706',
    colorError: '#dc2626',
    borderRadius: 10,
    borderRadiusLG: 16,
    fontFamily:
      "Inter, 'Segoe UI', 'Microsoft YaHei', system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
  },
  components: {
    Layout: {
      headerBg: 'transparent',
      bodyBg: 'transparent',
      siderBg: isDark ? '#0b1220' : '#f4f7fb',
    },
    Menu: {
      itemBorderRadius: 10,
      itemMarginInline: 10,
    },
    Card: {
      borderRadiusLG: 16,
    },
  },
})
