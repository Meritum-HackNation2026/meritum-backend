"""Privacy slice: a person deletes their checks in every channel.

Channels without a browser session (Discord, SMS, MCP) and the signed-in account
call ``delete_subject`` from ``meritum_backend.privacy.api``.

Features:
    US-BEZ-05, US-BEZ-06, US-POW-04, F-20
"""
