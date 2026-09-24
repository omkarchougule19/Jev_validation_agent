import os

import uvicorn

# Behind Render's proxy, trust X-Forwarded-For so per-IP limits see the
# visitor's address rather than the proxy's.
uvicorn.run("jev_guard.demo.app:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)),
            proxy_headers=True, forwarded_allow_ips="*")
