import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'NullState',
  tagline: 'Payment Infrastructure for AI Agents — x402, AP2, MCP, KYA. Open-source, self-hosted, multi-protocol.',
  favicon: 'img/favicon.svg',

  future: {
    v4: true,
  },

  url: 'https://nullstate.io',
  baseUrl: '/',

  organizationName: 'nullstate',
  projectName: 'nullstate',

  onBrokenLinks: 'warn',

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          editUrl: 'https://github.com/nullstate/nullstate/tree/main/website/',
        },
        blog: {
          showReadingTime: true,
          feedOptions: {
            type: ['rss', 'atom'],
            xslt: true,
          },
          editUrl: 'https://github.com/nullstate/nullstate/tree/main/website/',
          onInlineTags: 'warn',
          onInlineAuthors: 'warn',
          onUntruncatedBlogPosts: 'warn',
        },
        theme: {
          customCss: './src/css/custom.css',
        },
        sitemap: {
          lastmod: 'datetime',
          changefreq: 'weekly',
          priority: 0.5,
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    image: 'img/nullstate-social.svg',
    colorMode: {
      defaultMode: 'dark',
      respectPrefersColorScheme: true,
    },
    metadata: [
      {name: 'keywords', content: 'NullState, AI payment infrastructure, open-source AI payments, AI agent payments, x402 protocol, AP2 protocol, MCP protocol, KYA protocol, AI economy, agent payment system, AI agent economy, autonomous agent payments, USDC Solana micropayments'},
      {name: 'twitter:card', content: 'summary_large_image'},
      {name: 'twitter:title', content: 'NullState — Payment Infrastructure for AI Agents'},
      {name: 'twitter:description', content: 'NullState: Open-source payment infrastructure for AI agents. Secure, protocol-driven transactions (x402, AP2, MCP, KYA). Empowering AI economies.'},
      {name: 'twitter:site', content: '@NullState'},
      {name: 'og:title', content: 'NullState — Payment Infrastructure for AI Agents'},
      {name: 'og:description', content: 'Open-source payment infrastructure for AI agents. Secure, protocol-driven transactions (x402, AP2, MCP, KYA). Empowering AI economies.'},
      {name: 'og:type', content: 'website'},
      {name: 'og:image', content: 'https://greensol.me/nullstate/img/nullstate-social.svg'},
    ],
    navbar: {
      title: 'NullState',
      logo: {
        alt: 'NullState',
        src: 'img/logo.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'docsSidebar',
          position: 'left',
          label: 'Docs',
        },
        {to: '/blog', label: 'Blog', position: 'left'},
        {to: '/playground', label: 'Playground', position: 'left'},
        {to: '/pricing', label: 'Pricing', position: 'left'},
        {to: '/whitepaper', label: 'Whitepaper', position: 'left'},
        {to: '/about', label: 'About', position: 'left'},
        {
          href: 'https://github.com/nullstate/nullstate',
          position: 'right',
          className: 'header-github-link',
          'aria-label': 'GitHub',
        },
        {
          href: 'https://x.com/NullState',
          position: 'right',
          className: 'header-x-link',
          'aria-label': 'X / Twitter',
        },
        {
          href: 'https://greensol.me/nullstate/',
          label: 'Live Gateway',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Product',
          items: [
            {label: 'Quickstart', to: '/docs/quickstart'},
            {label: 'Pricing', to: '/pricing'},
            {label: 'Playground', to: '/playground'},
            {label: 'Brand', to: '/brand'},
          ],
        },
        {
          title: 'Protocols',
          items: [
            {label: 'x402', to: '/docs/protocols/x402'},
            {label: 'AP2', to: '/docs/protocols/ap2'},
            {label: 'MCP', to: '/docs/protocols/mcp'},
            {label: 'KYA', to: '/docs/protocols/kya'},
          ],
        },
        {
          title: 'Ecosystem',
          items: [
            {label: 'VS Code Extension', to: '/docs/extensions/vscode'},
            {label: 'MCP Hub', to: '/docs/extensions/mcp-hub'},
            {label: 'GitHub App', to: '/docs/extensions/github'},
            {label: 'Chrome Extension', to: '/docs/extensions/chrome'},
            {label: 'CLI Tool', to: '/docs/extensions/cli'},
            {label: 'HF Space', to: '/docs/extensions/huggingface'},
          ],
        },
        {
          title: 'Company',
          items: [
            {label: 'About', to: '/about'},
            {label: 'Blog', to: '/blog'},
            {label: 'Press Kit', to: '/press-kit'},
            {label: 'Brand', to: '/brand'},
            {label: 'GitHub', href: 'https://github.com/nullstate/nullstate'},
            {label: 'X / Twitter', href: 'https://x.com/NullState'},
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} NullState. MIT License. No State. No Limits. Everywhere.`,
    },
    prism: {
      theme: prismThemes.dracula,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'json', 'python', 'yaml'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
