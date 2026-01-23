"""
World generation for omphalOS.

This module provides world-building functionality with two modes:
1. Simple (legacy): Basic random generation for testing
2. Verisimilar: Realistic synthetic data with temporal/geographic patterns

Use verisimilar mode for demonstrations, research, and training.
"""

from .world_verisimilar import world_build_verisimilar, AOTA_DOMAINS

# Re-export for backward compatibility
def world_build(profile='national', out_dir='assets/world'):
    """
    Build a synthetic world for omphalOS analysis.

    This function now delegates to world_build_verisimilar for realistic data generation.

    Args:
        profile: Seed string for deterministic generation
        out_dir: Output directory for world files
    """
    world_build_verisimilar(profile=profile, out_dir=out_dir)
