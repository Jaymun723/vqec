"""Preload script for Dask workers to initialize VQEC adapters."""

def dask_setup(worker):
    from vqec.core.registry import scan_adapters
    from pathlib import Path
    
    # scan_adapters relative to this file
    adapters_dir = Path(__file__).parent / "adapters"
    scan_adapters(adapters_dir)
