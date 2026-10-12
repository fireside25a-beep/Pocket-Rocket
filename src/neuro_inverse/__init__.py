"""NeuroRoute Inverse AI research starter."""

# Optional classical Lbit/page scheduler. Importing the package never enables
# sparse execution by itself; callers must explicitly invoke ``plan_collapse``.
from .collapse_scheduler import (
    CouplingEdge, LbitExpert, OmissionCertificate, plan_collapse,
)
from .lbit_runtime import LbitMoEControlPlane, LbitPage, LbitSelection
from .ds4_runtime import (
    DS4LocalTransport, PRODUCT_CONTEXT_TOKENS, PRODUCT_MAX_NEW_TOKENS,
    QUALIFICATION_LADDER, SMOKE_CONTEXT_TOKENS, SMOKE_OUTPUT_TOKENS,
)
from .lumus_arh import (
    EphemeralHistoryEntry, EphemeralHistoryStore, EphemeralWorkerRecord,
    LocalModelTransport, LumusARHService, LumusARHWSGI, serve_loopback,
)
from .aegis_c2r import AegisC2R, C2RTranslation
from .aegis_runtime import AegisRuntime, AegisResult
from .agent_fabric import (
    CELL_COUNT, FABRIC_ROOT, FabricLimits, RecursiveFabricRuntime,
    classify_consensus, fabric_cells, plan_as_dict, plan_recursive, route_cells,
    verify_run_certificate, verify_trace_certificate, execute_recursive,
)

__all__ = [
    "AegisRuntime", "AegisResult", "AegisC2R", "C2RTranslation", "CouplingEdge", "LbitExpert", "LbitMoEControlPlane", "LbitPage",
    "LbitSelection", "OmissionCertificate", "plan_collapse",
    "EphemeralHistoryEntry", "EphemeralHistoryStore", "EphemeralWorkerRecord",
    "LocalModelTransport", "LumusARHService", "LumusARHWSGI", "serve_loopback",
    "DS4LocalTransport", "PRODUCT_CONTEXT_TOKENS", "PRODUCT_MAX_NEW_TOKENS",
    "QUALIFICATION_LADDER", "SMOKE_CONTEXT_TOKENS", "SMOKE_OUTPUT_TOKENS",
    "CELL_COUNT", "FABRIC_ROOT", "FabricLimits", "RecursiveFabricRuntime",
    "classify_consensus", "fabric_cells", "plan_as_dict", "plan_recursive", "route_cells",
    "verify_run_certificate", "verify_trace_certificate", "execute_recursive",
    "ExecutionPlan", "GovernanceReceipt", "create_receipt",
]

__version__ = "0.4.2"

from .execution_plan import ExecutionPlan
from .attest import GovernanceReceipt, create_receipt
