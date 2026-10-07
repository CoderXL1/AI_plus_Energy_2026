"""Download the pinned public data release and verify the recorded SHA256 checksums."""
from pathlib import Path
import urllib.request,json,hashlib,concurrent.futures
ROOT=Path(__file__).resolve().parents[1]
COMMIT='9b97ccbe90096aff42ed4fd6493bf7ae692d7118'
FILES=['data/metadata/metadata.csv','data/weather/weather.csv','data/meters/raw/electricity.csv']
def main():
    raw=ROOT/'data/raw';raw.mkdir(parents=True,exist_ok=True)
    known=json.loads((raw/'manifest.json').read_text()) if (raw/'manifest.json').exists() else []
    checks={r['file']:r['sha256'] for r in known if 'file' in r}
    def fetch(p):
        out=raw/Path(p).name;url=f'https://media.githubusercontent.com/media/buds-lab/building-data-genome-project-2/{COMMIT}/{p}'
        if not out.exists():
            with urllib.request.urlopen(url,timeout=120) as r,out.open('wb') as f:
                while b:=r.read(1024*1024):f.write(b)
        checksum=hashlib.sha256(out.read_bytes()).hexdigest()
        if out.name in checks:assert checksum==checks[out.name],f'Checksum mismatch: {out}'
        print(out.name,out.stat().st_size,checksum,flush=True)
        return dict(file=out.name,url=url,bytes=out.stat().st_size,sha256=checksum)
    with concurrent.futures.ThreadPoolExecutor(3) as pool:rows=list(pool.map(fetch,FILES))
    for name in ['LICENSE','README.md']:
        if not (raw/name).exists():
            (raw/name).write_bytes(urllib.request.urlopen(f'https://raw.githubusercontent.com/buds-lab/building-data-genome-project-2/{COMMIT}/{name}').read())
    if not known:(raw/'manifest.json').write_text(json.dumps(rows+[{'repository_commit':COMMIT}],indent=2))
if __name__=='__main__':main()
