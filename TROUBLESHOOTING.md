# Server Troubleshooting Guide

## Issue: "Server keeps crashing immediately"

### What's Actually Happening
The server runs in the foreground. Its startup banner alone does not confirm that it stayed running.

When you run:
```bash
python -m ats_matcher.server --mode gpu
```

The output you see is:
```
ATS Matcher: http://127.0.0.1:8765
CV reading: AI matching on GPU (Qwen_Qwen3-8B-Q4_K_M.gguf). Same matcher as ats-match parse.
Live job search and local application tracking. Loopback only. Ctrl+C to stop.
```

The PowerShell prompt should **not** return while this command is serving requests. Keep that terminal open. If the prompt returns, the process has stopped; check the error above the prompt and restart it before refreshing or searching.

### Silent exit on refresh or job search

The optional Indeed integration uses JobSpy and a native TLS library. On Windows that library can terminate its process without a Python traceback. Provider readiness checks now inspect package availability without importing JobSpy, and Indeed searches run in a separate worker process. If the worker fails, the app reports an Indeed source error and remains available.

Restart the app after updating:

```powershell
.\.venv\Scripts\python.exe -m ats_matcher.server --mode gpu
```

Open `http://127.0.0.1:8765` and leave the server terminal running. Use `--mode basic` if you want to run without a language model. If Indeed reports a worker failure, choose another source. For further silent-exit diagnostics, add `-X faulthandler` immediately after `python.exe` in the command above.

### How to Verify Server is Running

**Option 1: Open the web interface**
- Navigate to `http://localhost:8765` in your browser
- You should see the ATS Matcher app load

**Option 2: Test the API**
```bash
curl http://localhost:8765/api/providers
```

**Option 3: Check process**
```bash
# On Windows PowerShell
Get-Process python | Where-Object {$_.CommandLine -like "*server*"}

# On Linux/Mac
ps aux | grep server
```

### Stopping the Server
Press `Ctrl+C` in the terminal where the server is running.

## New API Endpoint: Provider Readiness

The `/api/providers` endpoint now includes readiness metadata:

**Request:**
```
GET http://localhost:8765/api/providers
```

**Response:**
```json
{
  "providers": [
    {
      "id": "linkedin",
      "label": "LinkedIn",
      "readiness": {
        "kind": "job_site",
        "available": true,
        "unavailable_reason": null,
        "configured_boards": 0,
        "supported_filters": ["keywords", "location", "workplace_type", ...],
        "unsupported_filters": ["career_url"],
        "default_date_behavior": "past_week",
        "countries": ["worldwide"],
        "requires_dependency": null,
        "last_check": "2026-09-15T15:30:00+00:00"
      }
    },
    {
      "id": "greenhouse",
      "label": "Greenhouse",
      "readiness": {
        "kind": "company_board",
        "available": true,
        "unavailable_reason": null,
        "configured_boards": 30,
        "supported_filters": ["keywords", "location", "date_since_posted"],
        ...
      }
    }
    ...
  ]
}
```

### What This Means

- **available**: Provider is ready to use
- **configured_boards**: Number of company boards loaded (company_board providers only)
- **requires_dependency**: What to install if unavailable (e.g., "python-jobspy" for Indeed)
- **supported_filters**: Which search filters this provider supports
- **kind**: Either "job_site" or "company_board"

## Testing the Updated System

### 1. Test Location Matching
```bash
python -c "
from ats_matcher.geo import locations_match_flexible
print(locations_match_flexible('Berlin', 'Berlin, Germany'))  # True
print(locations_match_flexible('Berlin', 'Amsterdam'))        # False
"
```

### 2. Test Company Registry
```bash
python -c "
from ats_matcher.jobs.company_registry import CompanyRegistry
cr = CompanyRegistry()
print(f'Total: {len(cr.list_all())} companies')
print(f'Greenhouse: {len(cr.list_by_ats(\"greenhouse\"))} boards')
"
```

### 3. Test Provider Readiness
```bash
python -c "
from ats_matcher.jobs.registry import default_registry
from ats_matcher.config import Settings
registry = default_registry(Settings())
for p in registry.list_with_readiness():
    print(f'{p[\"id\"]}: available={p[\"readiness\"][\"available\"]}, boards={p[\"readiness\"][\"configured_boards\"]}')
"
```

## Common Issues

### Issue: "Port 8765 already in use"
**Solution**: Stop the existing server or use a different port:
```bash
python -m ats_matcher.server --port 8766
```

### Issue: Model file not found (for GPU/CPU mode)
**Solution**: Use basic mode which doesn't require a model:
```bash
python -m ats_matcher.server --mode basic
```

Or point to your model:
```bash
python -m ats_matcher.server --mode gpu --model path/to/model.gguf
```

### Issue: Browser can't connect
**Solutions**:
- Ensure you're using `localhost` or `127.0.0.1` (not external IP)
- Check firewall isn't blocking port 8765
- Verify server process is still running
- Try a different port and check if that works

## Performance Notes

- Server startup: ~2-5 seconds
- First request: ~1-2 seconds (model loads on first request)
- Subsequent requests: <100ms for API, <200ms for searches
- Memory: ~500MB base + model size (for GPU/CPU mode)

