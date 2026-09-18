import sys
sys.path.insert(0, r'C:\Users\11csh\zhahi\visionguard\backend')
from app.main import app

print('All routes:')
routes = sorted([r.path for r in app.routes if hasattr(r, 'methods') and r.methods])
for r in routes:
    print(f'  {r}')

print()
print('Key route verification:')
key_routes = ['/health', '/api/v1/system/status', '/api/v1/monitoring/start', '/api/v1/monitoring/stop', '/api/v1/monitoring/status']
for k in key_routes:
    present = k in routes
    status = 'PRESENT' if present else 'MISSING'
    print(f'  {k}: {status}')