"""NullStateChief — Google ADK agent definition for infrastructure operations.
"""
from google.adk.agents import LlmAgent
from google.adk.tools import agent_tool
from google.adk.tools.google_search_tool import GoogleSearchTool
from google.adk.tools import url_context

subagent_google_search_agent = LlmAgent(
    name="Subagent_google_search_agent",
    model="gemini-2.5-flash",
    description="Agent specialized in performing Google searches.",
    sub_agents=[],
    instruction="Use the GoogleSearchTool to find information on the web.",
    tools=[GoogleSearchTool()],
)
subagent_url_context_agent = LlmAgent(
    name="Subagent_url_context_agent",
    model="gemini-2.5-flash",
    description="Agent specialized in fetching content from URLs.",
    sub_agents=[],
    instruction="Use the UrlContextTool to retrieve content from provided URLs.",
    tools=[url_context],
)
subagent = LlmAgent(
    name="subagent",
    model="gemini-2.5-flash",
    description="General-purpose subagent with search and URL tools.",
    sub_agents=[],
    instruction="",
    tools=[
        agent_tool.AgentTool(agent=subagent_google_search_agent),
        agent_tool.AgentTool(agent=subagent_url_context_agent),
    ],
)
null_state_chief_google_search_agent = LlmAgent(
    name="NullStateChief_google_search_agent",
    model="gemini-2.5-pro",
    description="Agent specialized in performing Google searches.",
    sub_agents=[],
    instruction="Use the GoogleSearchTool to find information on the web.",
    tools=[GoogleSearchTool()],
)
null_state_chief_url_context_agent = LlmAgent(
    name="NullStateChief_url_context_agent",
    model="gemini-2.5-pro",
    description="Agent specialized in fetching content from URLs.",
    sub_agents=[],
    instruction="Use the UrlContextTool to retrieve content from provided URLs.",
    tools=[url_context],
)
root_agent = LlmAgent(
    name="NullStateChief",
    model="gemini-2.5-pro",
    description="Advanced infrastructure agent for systems optimization, cloud monitoring, and automated workflow troubleshooting across GCP and Windows Server 2025.",
    sub_agents=[subagent],
    instruction="""# Role & Persona
You are \"NullState-Ops-Agent\", an expert Cloud DevOps and Systems Infrastructure specialist.
You specialize in Google Cloud Platform (GCP), high-performance compute tuning, and Windows Server 2025 optimization.
Your tone is technical, concise, sharp, and highly efficient.

# Objectives
1. Help users monitor, optimize, and manage virtual machines (specifically high-memory configurations like 128 GB RAM instances).
2. Provide step-by-step guidance for system administration tasks (such as Windows pagefile restriction, disk IOPS upgrades, and network security policies).
3. Identify potential cost bottlenecks in infrastructure configurations (e.g., alert users when core licensing fees scale unnecessarily).

# Operational Guardrails
- NEVER suggest destructive operations (like deleting disks or stopping critical instances) without explicitly warning the user about data retention policies first.
- If a user asks to modify cloud infrastructure directly via commands, always verify if their active environment has the correct Google API scopes (e.g., checking if the Compute Engine API is disabled or enabled for the service account).
- Prioritize security best practices, explicitly calling out open public ports (0.0.0.0/0) or default service account vulnerabilities.

# Output Formatting
- Use clear Markdown headings, tables for hardware comparisons, and clean code blocks for terminal commands (PowerShell, Bash, or gcloud CLI).
- Break complex system tasks into numbered, logical steps.""",
    tools=[
        agent_tool.AgentTool(agent=null_state_chief_google_search_agent),
        agent_tool.AgentTool(agent=null_state_chief_url_context_agent),
    ],
)
