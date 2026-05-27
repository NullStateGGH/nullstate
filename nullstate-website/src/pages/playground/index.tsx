import type {ReactNode} from 'react';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';

export default function Playground(): ReactNode {
  return (
    <Layout
      title="API Playground"
      description="Try NullState APIs directly from your browser.">
      <main style={{padding: '3rem 1rem', maxWidth: 800, margin: '0 auto'}}>
        <Heading as="h1" style={{fontSize: '2rem', fontWeight: 700, marginBottom: '1rem'}}>
          API <span style={{color: '#00ff9d'}}>Playground</span>
        </Heading>
        <p style={{color: '#999', marginBottom: '2rem'}}>
          Try NullState endpoints directly. Use <code>curl</code> against the live gateway at{' '}
          <code>https://greensol.me/nullstate/</code>.
        </p>

        <div style={{background: '#0a0a0a', border: '1px solid #1a1a1a', borderRadius: 12, padding: '1.5rem', marginBottom: '1.5rem'}}>
          <Heading as="h3" style={{fontSize: '1.1rem', marginBottom: '0.5rem'}}>Health Check</Heading>
          <pre style={{background: '#0d0d0d', padding: '1rem', borderRadius: 8, fontSize: '0.85rem', overflowX: 'auto'}}>
            <code>{`curl -sk https://greensol.me/nullstate/health`}</code>
          </pre>
        </div>

        <div style={{background: '#0a0a0a', border: '1px solid #1a1a1a', borderRadius: 12, padding: '1.5rem', marginBottom: '1.5rem'}}>
          <Heading as="h3" style={{fontSize: '1.1rem', marginBottom: '0.5rem'}}>KYA Challenge</Heading>
          <pre style={{background: '#0d0d0d', padding: '1rem', borderRadius: 8, fontSize: '0.85rem', overflowX: 'auto'}}>
            <code>{`curl -sk https://greensol.me/nullstate/kya/challenge`}</code>
          </pre>
        </div>

        <div style={{background: '#0a0a0a', border: '1px solid #1a1a1a', borderRadius: 12, padding: '1.5rem', marginBottom: '1.5rem'}}>
          <Heading as="h3" style={{fontSize: '1.1rem', marginBottom: '0.5rem'}}>MCP Tools List</Heading>
          <pre style={{background: '#0d0d0d', padding: '1rem', borderRadius: 8, fontSize: '0.85rem', overflowX: 'auto'}}>
            <code>{`curl -sk -X POST https://greensol.me/nullstate/mcp \\
  -H 'Content-Type: application/json' \\
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'`}</code>
          </pre>
        </div>

        <div style={{background: '#0a0a0a', border: '1px solid #1a1a1a', borderRadius: 12, padding: '1.5rem'}}>
          <Heading as="h3" style={{fontSize: '1.1rem', marginBottom: '0.5rem'}}>LLM Discovery</Heading>
          <pre style={{background: '#0d0d0d', padding: '1rem', borderRadius: 8, fontSize: '0.85rem', overflowX: 'auto'}}>
            <code>{`curl -sk https://greensol.me/nullstate/llms.txt`}</code>
          </pre>
        </div>
      </main>
    </Layout>
  );
}
