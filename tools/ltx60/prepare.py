"""Copy the explicitly selected native-60 LTX experiment without changing defaults."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    config = json.loads((ROOT / 'config/appsettings.json').read_text(encoding='utf-8-sig'))
    source = ROOT / 'tools/ltx60/ltx_native60_experiment_api.json'
    target = Path(config['Paths']['Workflows']) / source.name
    if target.exists():
        if target.read_bytes() != source.read_bytes():
            raise RuntimeError('Existing experiment workflow differs; preserved')
    else:
        with target.open('xb') as output:
            output.write(source.read_bytes())
    print(json.dumps({'workflow': target.name, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
