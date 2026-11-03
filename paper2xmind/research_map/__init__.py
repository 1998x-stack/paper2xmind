"""Deterministic source-backed presentation of paper research."""
from .contracts import MAP_SCHEMA_VERSION, MapNode, MapEdge, ResearchMap
from .projector import project_research_map, validate_research_map
__all__ = ["MAP_SCHEMA_VERSION", "MapNode", "MapEdge", "ResearchMap", "project_research_map", "validate_research_map"]
