import sys
sys.path.insert(0, r'C:\Users\11csh\zhahi\visionguard\backend')
from app.main import app

print('Routes:')
for r in app.routes:
    if hasattr(r, 'methods') and r.methods:
        print(f'  {r.methods} {r.path}')
    else:
        print(f'  {type(r).__name__} (no methods)')