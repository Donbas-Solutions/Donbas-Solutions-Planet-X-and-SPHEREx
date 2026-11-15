"""HTTP routes of the API (docs/api.md). Endpoints stay thin: parse, call a domain function, return a model."""

from fastapi import APIRouter

from . import health, overlays, resolve, sequences, spectra

ROUTERS: tuple[APIRouter, ...] = (
    health.router,
    resolve.router,
    sequences.router,
    spectra.router,
    overlays.router,
)
