import type {ReactNode} from 'react';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import Link from '@docusaurus/Link';
import Heading from '@theme/Heading';

const protocols = [
  {name: 'x402', desc: 'HTTP 402 crypto micropayments via USDC on Solana', tag: 'Live', color: '#00ff9d'},
  {name: 'AP2', desc: 'Enterprise agent-to-agent mandates with RSA-2048 signing', tag: 'Live', color: '#4d9eff'},
  {name: 'MCP', desc: 'Model Context Protocol — tools, resources, JSON-RPC 2.0', tag: 'Live', color: '#ff6b6b'},
  {name: 'KYA', desc: 'Know-Your-Agent identity via RSA-2048 challenge/response', tag: 'Live', color: '#ffd93d'},
];

const features = [
  {icon: '⚡', title: 'Zero Setup', desc: 'docker compose up -d. That is it. Your payment gateway is live in 30 seconds.'},
  {icon: '🔓', title: 'Your Keys, Your State', desc: 'Self-hosted. MIT licensed. No vendor. No tax. No permission required.'},
  {icon: '🔄', title: 'Multi-Protocol', desc: 'x402, AP2, MCP, KYA — agents speak their native protocol, you collect in USDC.'},
  {icon: '🤖', title: 'AI-Native', desc: 'Dual-model intelligence (Phi-3 + Gemini). Graceful degradation. Always running.'},
  {icon: '🔌', title: 'Creeps Into Everything', desc: 'VS Code, GitHub, Chrome, CLI, MCP Hub, Hugging Face — we exist in every ecosystem.'},
  {icon: '🛡️', title: 'Self-Custodial', desc: 'Private keys never leave your infra. Non-custodial. Non-negotiable.'},
];

const extensions = [
  {name: 'VS Code Extension', desc: 'Agent workspace with sandboxed terminal + built-in MCP payment', href: '#'},
  {name: 'MCP Hub', desc: 'Auto-discovers MCP servers, wraps with payment layer', href: '#'},
  {name: 'GitHub App', desc: 'Auto-settle agent work in CI/CD pipelines', href: '#'},
  {name: 'Chrome Extension', desc: 'Injects KYA into Gemini API calls', href: '#'},
  {name: 'CLI Tool', desc: 'Full gateway management from terminal', href: '#'},
  {name: 'Hugging Face Space', desc: 'Pay-per-call HF Inference via NullState', href: '#'},
];

const stats = [
  {value: '$8.8B+', label: 'Agent Transaction Volume 2025'},
  {value: '128', label: 'Tasks Settled Today'},
  {value: '$8.99', label: 'Current Ledger Balance'},
  {value: '0', label: 'Days Until You Deploy'},
];

function HomepageHeader() {
  return (
    <header className="hero" style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'radial-gradient(ellipse at 50% 0%, #0a2a1a 0%, #030303 50%)',
      padding: '4rem 1rem',
    }}>
      <div className="container" style={{textAlign: 'center'}}>
        <div style={{marginBottom: '2rem'}}>
          <svg width="80" height="80" viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg" style={{display: 'inline-block'}}>
            <circle cx="40" cy="40" r="30" stroke="#00ff9d" strokeWidth="3" fill="none"/>
            <circle cx="40" cy="40" r="14" stroke="#00ff9d" strokeWidth="3" fill="none"/>
            <line x1="14" y1="14" x2="66" y2="66" stroke="#00ff9d" strokeWidth="2.5" strokeLinecap="round"/>
          </svg>
        </div>
        <p style={{color: '#00ff9d', fontSize: '0.8rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '3px', marginBottom: '1rem'}}>
          Open Source · Self-Hosted · Multi-Protocol
        </p>
        <Heading as="h1" className="hero__title" style={{fontSize: 'clamp(2.5rem, 6vw, 4.5rem)', lineHeight: 1.1}}>
          Payment Infrastructure<br />for <span style={{color: '#00ff9d'}}>AI Agents</span>
        </Heading>
        <p style={{fontSize: '1.15rem', color: '#888', maxWidth: '560px', margin: '1.5rem auto', lineHeight: 1.6}}>
          The agent economy needs a settlement layer. Not a promise. Not a roadmap.<br />
          <strong style={{color: '#ccc'}}>x402, AP2, MCP, KYA — one open-source commerce layer. Live today.</strong>
        </p>
        <div className="buttons" style={{gap: '0.75rem'}}>
          <Link className="button button--primary button--lg" to="/docs/quickstart" style={{padding: '0.85rem 2rem', fontSize: '1rem'}}>
            Deploy in 30 Seconds →
          </Link>
          <Link className="button button--secondary button--lg" to="https://github.com/nullstate/nullstate" style={{padding: '0.85rem 2rem', fontSize: '1rem'}}>
            View on GitHub
          </Link>
          <Link className="button button--secondary button--lg" to="/docs/protocols/mcp" style={{padding: '0.85rem 2rem', fontSize: '1rem'}}>
            MCP Server
          </Link>
        </div>
        <div style={{marginTop: '3rem', fontSize: '0.8rem', color: '#444'}}>
          <span style={{color: '#00ff9d'}}>$</span> docker compose up -d · <span style={{color: '#00ff9d'}}>$</span> curl localhost:8080/health
        </div>
      </div>
    </header>
  );
}

function ProtocolsSection() {
  return (
    <section style={{padding: '6rem 0', borderTop: '1px solid #0a0a0a'}}>
      <div className="container">
        <div style={{textAlign: 'center', marginBottom: '3rem'}}>
          <Heading as="h2" style={{fontSize: '2rem', fontWeight: 700, marginBottom: '0.75rem'}}>
            Multi-<span style={{color: '#00ff9d'}}>Protocol</span> by Design
          </Heading>
          <p style={{color: '#666', maxWidth: '500px', margin: '0 auto'}}>
            Four protocols. One gateway. Any agent can pay, any agent can collect.
          </p>
        </div>
        <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem'}}>
          {protocols.map((p) => (
            <div key={p.name} className="card" style={{padding: '1.5rem', background: '#080808', border: '1px solid #111'}}>
              <div style={{display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem'}}>
                <div style={{width: '8px', height: '8px', borderRadius: '50%', background: p.color}} />
                <Heading as="h3" style={{fontSize: '1.1rem', margin: 0}}>{p.name}</Heading>
              </div>
              <p style={{fontSize: '0.85rem', color: '#666', marginBottom: '0.75rem'}}>{p.desc}</p>
              <span style={{fontSize: '0.7rem', padding: '2px 8px', borderRadius: '4px', background: 'rgba(0,255,157,0.08)', color: '#00ff9d'}}>{p.tag}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function TerminalSection() {
  return (
    <section style={{padding: '3rem 0', borderTop: '1px solid #0a0a0a'}}>
      <div className="container">
        <div style={{textAlign: 'center', marginBottom: '2rem'}}>
          <Heading as="h2" style={{fontSize: '2rem', fontWeight: 700, marginBottom: '0.5rem'}}>
            Deploy. <span style={{color: '#00ff9d'}}>Now.</span>
          </Heading>
          <p style={{color: '#666'}}>Zero dependencies. Zero configuration. Zero excuses.</p>
        </div>
        <div style={{
          background: '#060606',
          border: '1px solid #111',
          borderRadius: '12px',
          padding: '1.5rem',
          fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
          fontSize: '0.85rem',
          lineHeight: '2',
          overflowX: 'auto',
          maxWidth: '680px',
          margin: '0 auto',
        }}>
          <div style={{color: '#444'}}># Deploy NullState in 30 seconds</div>
          <div><span style={{color: '#00ff9d'}}>$</span> docker compose up -d</div>
          <div><span style={{color: '#00ff9d'}}>$</span> curl https://localhost:8080/health</div>
          <div style={{color: '#777'}}>{'{ "status": "ok", "balance": "0.46 USDC", "tasks": 16, "protocols": ["x402", "ap2", "mcp", "kya"] }'}</div>
          <div style={{marginTop: '0.75rem', color: '#444'}}># AP2 Handshake (3 lines, no BS)</div>
          <div><span style={{color: '#00ff9d'}}>$</span> python3 examples/five_minute_store.py</div>
          <div style={{color: '#777'}}>{'[OK] Signed CartMandate → PaymentMandate → Settled (0.025 USDC)'}</div>
        </div>
      </div>
    </section>
  );
}

function FeaturesSection() {
  return (
    <section style={{padding: '6rem 0', borderTop: '1px solid #0a0a0a'}}>
      <div className="container">
        <div style={{textAlign: 'center', marginBottom: '3rem'}}>
          <Heading as="h2" style={{fontSize: '2rem', fontWeight: 700, marginBottom: '0.75rem'}}>
            Built for the <span style={{color: '#00ff9d'}}>Agent Economy</span>
          </Heading>
          <p style={{color: '#666', maxWidth: '500px', margin: '0 auto'}}>
            Not a side project. Not a hackathon demo. Production infrastructure.
          </p>
        </div>
        <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1rem'}}>
          {features.map((f) => (
            <div key={f.title} className="card" style={{padding: '2rem', background: '#080808', border: '1px solid #111'}}>
              <div style={{fontSize: '1.5rem', marginBottom: '0.75rem'}}>{f.icon}</div>
              <Heading as="h3" style={{fontSize: '1rem', marginBottom: '0.4rem'}}>{f.title}</Heading>
              <p style={{fontSize: '0.85rem', color: '#666', lineHeight: 1.5, margin: 0}}>{f.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function EcosystemSection() {
  return (
    <section style={{padding: '6rem 0', borderTop: '1px solid #0a0a0a'}}>
      <div className="container">
        <div style={{textAlign: 'center', marginBottom: '3rem'}}>
          <Heading as="h2" style={{fontSize: '2rem', fontWeight: 700, marginBottom: '0.75rem'}}>
            We Creep Into <span style={{color: '#00ff9d'}}>Everything</span>
          </Heading>
          <p style={{color: '#666', maxWidth: '500px', margin: '0 auto'}}>
            VS Code. GitHub. Chrome. CLI. MCP. Hugging Face.<br />
            <strong style={{color: '#888'}}>No state. No boundaries. Everywhere.</strong>
          </p>
        </div>
        <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '1rem'}}>
          {extensions.map((e) => (
            <div key={e.name} className="card" style={{padding: '1.5rem', background: '#080808', border: '1px solid #111'}}>
              <Heading as="h3" style={{fontSize: '0.95rem', marginBottom: '0.4rem'}}>{e.name}</Heading>
              <p style={{fontSize: '0.8rem', color: '#666', marginBottom: '0', lineHeight: 1.4}}>{e.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function StatsSection() {
  return (
    <section style={{padding: '6rem 0', borderTop: '1px solid #0a0a0a', borderBottom: '1px solid #0a0a0a'}}>
      <div className="container">
        <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.5rem', textAlign: 'center'}}>
          {stats.map((s) => (
            <div key={s.label}>
              <div style={{fontSize: '2.8rem', fontWeight: 800, color: '#00ff9d', lineHeight: 1, marginBottom: '0.5rem'}}>{s.value}</div>
              <div style={{fontSize: '0.8rem', color: '#555', textTransform: 'uppercase', letterSpacing: '1px'}}>{s.label}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function CtaSection() {
  return (
    <section style={{padding: '6rem 0', textAlign: 'center'}}>
      <div className="container">
        <Heading as="h2" style={{fontSize: '2.2rem', fontWeight: 700, marginBottom: '1rem'}}>
          We Are <span style={{color: '#00ff9d'}}>State</span>.
        </Heading>
        <p style={{color: '#666', fontSize: '1.1rem', marginBottom: '0.5rem', maxWidth: '500px', margin: '0 auto 1.5rem'}}>
          No boundaries. No limits. No permission required.<br />
          The agent economy doesn't wait for incumbents.
        </p>
        <div className="buttons" style={{gap: '0.75rem', justifyContent: 'center'}}>
          <Link className="button button--primary button--lg" to="/docs/quickstart" style={{padding: '0.85rem 2.5rem', fontSize: '1rem'}}>
            Deploy Now →
          </Link>
          <Link className="button button--secondary button--lg" to="/blog" style={{padding: '0.85rem 2.5rem', fontSize: '1rem'}}>
            Read the Manifesto
          </Link>
        </div>
      </div>
    </section>
  );
}

export default function Home(): ReactNode {
  const {siteConfig} = useDocusaurusContext();
  return (
    <Layout
      title={siteConfig.tagline}
      description="NullState is an open-source, multi-protocol commerce layer for AI agents. x402 for crypto micropayments, AP2 for enterprise mandates, MCP for AI tool integration, KYA for agent identity. Self-hosted, zero-dependency, production-ready.">
      <HomepageHeader />
      <main>
        <StatsSection />
        <ProtocolsSection />
        <TerminalSection />
        <FeaturesSection />
        <EcosystemSection />
        <CtaSection />
      </main>
    </Layout>
  );
}
