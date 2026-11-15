"""Shared resources created in `main.lifespan`, handed to endpoints through `Depends`."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from ..archive.collections import CollectionDiscovery
from ..archive.gaia import GaiaCatalog
from ..archive.http import Http
from ..archive.resolve import Resolver
from ..jobs import JobRunner


def get_runner(request: Request) -> JobRunner:
    runner: JobRunner = request.app.state.runner
    return runner


def get_discovery(request: Request) -> CollectionDiscovery:
    discovery: CollectionDiscovery = request.app.state.discovery
    return discovery


def get_http(request: Request) -> Http:
    http: Http = request.app.state.http
    return http


def get_resolver(request: Request) -> Resolver:
    resolver: Resolver = request.app.state.resolver
    return resolver


def get_gaia(request: Request) -> GaiaCatalog:
    gaia: GaiaCatalog = request.app.state.gaia
    return gaia


Runner = Annotated[JobRunner, Depends(get_runner)]
SharedHttp = Annotated[Http, Depends(get_http)]
NameResolver = Annotated[Resolver, Depends(get_resolver)]
Discovery = Annotated[CollectionDiscovery, Depends(get_discovery)]
Gaia = Annotated[GaiaCatalog, Depends(get_gaia)]
