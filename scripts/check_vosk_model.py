import sys, traceback
from pathlib import Path
p = Path('models/vosk-model-ru-0.42')
print('cwd:', Path.cwd())
print('model path (resolved):', p.resolve())
print('model exists:', p.exists())
if p.exists():
    try:
        print('top-level entries:')
        for i,e in enumerate(p.iterdir()):
            print('-', e.name)
            if i>20:
                break
    except Exception as e:
        print('listing error', e)
try:
    from vosk import Model
    print('vosk imported OK')
    try:
        m = Model(str(p))
        print('Model loaded OK')
    except Exception as e:
        print('Model load error:')
        traceback.print_exc()
except Exception as e:
    print('vosk import failed:')
    traceback.print_exc()
print('sys.executable:', sys.executable)
print('python version:', sys.version)
