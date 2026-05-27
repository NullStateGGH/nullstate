import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docsSidebar: [
    'quickstart',
    {
      type: 'category',
      label: 'Protocols',
      items: [
        'protocols/x402',
        'protocols/ap2',
        'protocols/mcp',
        'protocols/kya',
      ],
    },
    {
      type: 'category',
      label: 'Gateway API',
      items: [
        'gateway/overview',
        'gateway/endpoints',
        'gateway/authentication',
        'gateway/rate-limiting',
        'gateway/errors',
      ],
    },
    {
      type: 'category',
      label: 'MCP Server',
      link: { type: 'doc', id: 'mcp-server/overview' },
      items: [
        'mcp-server/overview',
        'mcp-server/tools',
        'mcp-server/resources',
        'mcp-server/proxy',
      ],
    },
    {
      type: 'category',
      label: 'Deployment',
      items: [
        'deployment/quickstart',
        'deployment/docker',
        'deployment/systemd',
        'deployment/configuration',
        'deployment/security',
      ],
    },
    'architecture',
    'faq',
  ],
};

export default sidebars;
