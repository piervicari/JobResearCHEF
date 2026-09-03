#!/usr/bin/env python3
"""Compatibility wrapper for the Milestone 1 validation CLI."""

from research_agent.cli import app

if __name__ == "__main__":
    app(["validate-master"])
