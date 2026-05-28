"""NullState HOD (Hierarchical Orchestration & Delegation) System.
Autonomous task management — reads queues, delegates work, tracks costs, self-improves.
The system runs itself. No manual control. No boundaries.
"""

from .engine import HODEngine, CostLedger, TaskDelegator
