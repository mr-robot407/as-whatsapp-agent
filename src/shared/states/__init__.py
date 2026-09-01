"""Per-state handlers for the WhatsApp funnel.

Each module exposes one or more `handle_*` functions with the signature:
    handle(ctx: RouterContext) -> str   # returns next state_id

Router (`src/shared/router.py`) owns dispatch and state persistence; handlers
own only the "given this message, what do we send and where do we go next"
logic.
"""
