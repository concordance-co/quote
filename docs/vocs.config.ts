import { defineConfig } from 'vocs'

export default defineConfig({
  title: 'Docs',
  sidebar: [
    {
      text: 'Getting Started',
      link: '/getting-started',
    },
    {
      text: 'CLI',
      link: '/cli',
    },
    {
      text: 'Engine',
      collapsed: true,
      items: [
        { text: 'Overview', link: '/engine' },
        { text: 'Building Mods', link: '/engine/building-mods' },
        { text: 'SDK', link: '/engine/sdk' },
        { text: 'Shared Types', link: '/engine/shared' },
        { text: 'Self Prompt', link: '/engine/self-prompt' },
        { text: 'Strategies', link: '/engine/strategies' },
        { text: 'Flow', link: '/engine/flow' },
      ],
    },
  ],
})
