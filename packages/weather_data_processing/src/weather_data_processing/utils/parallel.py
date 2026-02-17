# =============================================================================
# Copyright © 2025 Daniel Kaupa
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

"""
Parallel Compute Environment Detection
=======================================

Auto-detect compute environment (local, PBS, SLURM, MPI) and recommend
optimal parallelization settings.

This module enables the pipeline to automatically adapt to the execution
environment without manual configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional


@dataclass
class ComputeEnvironment:
    """
    Detected compute environment configuration.
    
    Attributes
    ----------
    backend : {'local', 'pbs', 'slurm', 'mpi'}
        Detected execution environment type.
    total_cores : int
        Total CPU cores available on this machine/node.
    available_ranks : int or None
        Number of MPI ranks allocated (for distributed jobs).
    node_count : int or None
        Number of compute nodes allocated.
    nodefile_path : Path or None
        Path to the PBS/SLURM nodefile, if applicable.
    """
    
    backend: Literal["local", "pbs", "slurm", "mpi"]
    total_cores: int
    available_ranks: Optional[int] = None
    node_count: Optional[int] = None
    nodefile_path: Optional[Path] = None
    
    def recommended_workers(
        self,
        task_type: str = "cpu",
        cap_fraction: float = 0.75
    ) -> int:
        """
        Recommend worker count based on task type and environment.
        
        Parameters
        ----------
        task_type : str, optional
            Type of task: 'cpu', 'io', 'memory'. Default is 'cpu'.
        cap_fraction : float, optional
            For local execution, fraction of cores to use (default 0.75
            to avoid freezing the system).
        
        Returns
        -------
        int
            Recommended number of workers.
        """
        if self.backend == "local":
            # Cap at cap_fraction for local machines to avoid system freeze
            return max(1, int(self.total_cores * cap_fraction))
        
        elif self.backend in ("pbs", "slurm", "mpi"):
            # Use all allocated resources on HPC
            return self.available_ranks or self.total_cores
        
        return max(1, self.total_cores)
    
    def __str__(self) -> str:
        """Return human-readable environment description."""
        lines = [
            f"Compute Environment: {self.backend.upper()}",
            f"  Total cores: {self.total_cores}",
        ]
        if self.available_ranks is not None:
            lines.append(f"  MPI ranks: {self.available_ranks}")
        if self.node_count is not None:
            lines.append(f"  Nodes: {self.node_count}")
        if self.nodefile_path is not None:
            lines.append(f"  Nodefile: {self.nodefile_path}")
        return "\n".join(lines)


def detect_environment() -> ComputeEnvironment:
    """
    Auto-detect the current compute environment.
    
    Detection order:
    1. PBS (via $PBS_NODEFILE)
    2. SLURM (via $SLURM_JOB_ID)
    3. Generic MPI (via $OMPI_COMM_WORLD_SIZE or $PMI_SIZE)
    4. Local machine (fallback)
    
    Returns
    -------
    ComputeEnvironment
        Detected environment configuration.
    
    Examples
    --------
    >>> env = detect_environment()
    >>> print(env)
    Compute Environment: PBS
      Total cores: 128
      MPI ranks: 30
      Nodes: 2
    
    >>> workers = env.recommended_workers()
    >>> print(f"Using {workers} workers")
    Using 30 workers
    """
    # -----------------------------------------------------------------
    # PBS Detection
    # -----------------------------------------------------------------
    pbs_nodefile = os.getenv("PBS_NODEFILE")
    if pbs_nodefile:
        nodefile_path = Path(pbs_nodefile)
        if nodefile_path.exists():
            lines = nodefile_path.read_text().strip().split("\n")
            ranks = len(lines)
            unique_nodes = len(set(lines))
            
            return ComputeEnvironment(
                backend="pbs",
                total_cores=os.cpu_count() or 1,
                available_ranks=ranks,
                node_count=unique_nodes,
                nodefile_path=nodefile_path
            )
    
    # -----------------------------------------------------------------
    # SLURM Detection
    # -----------------------------------------------------------------
    if os.getenv("SLURM_JOB_ID"):
        return ComputeEnvironment(
            backend="slurm",
            total_cores=int(os.getenv("SLURM_CPUS_ON_NODE", os.cpu_count() or 1)),
            available_ranks=int(os.getenv("SLURM_NTASKS", 1)),
            node_count=int(os.getenv("SLURM_NNODES", 1))
        )
    
    # -----------------------------------------------------------------
    # Generic MPI Detection
    # -----------------------------------------------------------------
    mpi_size = os.getenv("OMPI_COMM_WORLD_SIZE") or os.getenv("PMI_SIZE")
    if mpi_size:
        return ComputeEnvironment(
            backend="mpi",
            total_cores=os.cpu_count() or 1,
            available_ranks=int(mpi_size),
            node_count=None
        )
    
    # -----------------------------------------------------------------
    # Local Machine (Fallback)
    # -----------------------------------------------------------------
    return ComputeEnvironment(
        backend="local",
        total_cores=os.cpu_count() or 1,
        available_ranks=None,
        node_count=1
    )


def get_mpi_rank() -> int:
    """
    Get the current MPI rank (if running under MPI).
    
    Returns
    -------
    int
        MPI rank (0-indexed). Returns 0 if not running under MPI.
    
    Examples
    --------
    >>> rank = get_mpi_rank()
    >>> print(f"I am rank {rank}")
    I am rank 0
    """
    # Try different MPI implementations
    for var in ["OMPI_COMM_WORLD_RANK", "PMI_RANK", "SLURM_PROCID"]:
        val = os.getenv(var)
        if val is not None:
            return int(val)
    
    return 0


def is_rank_zero() -> bool:
    """
    Check if this is the master/root process (rank 0).
    
    Returns
    -------
    bool
        True if this is rank 0 or not running under MPI.
    """
    return get_mpi_rank() == 0
