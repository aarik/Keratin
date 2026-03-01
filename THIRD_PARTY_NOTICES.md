# Third-Party Notices

This project incorporates and adapts work from the following open-source projects.  
Their original license texts are preserved in `third_party/`.

## rhino-mcp

- Copyright: 2025 Reer
- License: MIT (see `third_party/rhino-mcp/LICENSE`)
- Upstream README states the project is developed by REER, INC.
- Upstream references:
  - PyPI: https://pypi.org/project/reer-rhino-mcp/
  - MCP resources referenced by upstream: https://modelcontextprotocol.io/
  - Upstream inspiration reference: https://github.com/ahujasid/blender-mcp

## rhinomcp

- Author: Jingcheng Chen (GitHub: https://github.com/jingcheng-chen)
- Repository: https://github.com/jingcheng-chen/rhinomcp
- License: Apache License 2.0 (see `third_party/rhinomcp/LICENSE`)

## What was changed in this project

This project focuses on a stability-first Rhino 7 execution model while expanding the tool surface area inspired by the upstream projects above. In particular:

- Maintains Rhino-safe, main-thread document operations (via Rhino Idle execution).
- Uses newline-delimited JSON for request/response framing over TCP sockets.
- Exposes additional MCP tools for document inspection, object/layer control, and common geometry operations.



## always-tinkering/rhinoMcpServer (inspiration)

- Upstream repository: https://github.com/always-tinkering/rhinoMcpServer
- Notes: This repo did not include a LICENSE file in the root at the time of review (the README states MIT). To avoid license ambiguity, this project **does not copy code verbatim** from that repo. Instead, it re-implements similar diagnostic/log-ops functionality from scratch, inspired by the upstream project’s structure and intent.
