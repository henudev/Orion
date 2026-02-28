from __future__ import annotations

import asyncio
from collections import defaultdict


deploy_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

