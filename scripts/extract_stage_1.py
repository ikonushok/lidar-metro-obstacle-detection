"""Extract only the two selected bags; never overwrite an existing file."""
import argparse
from pathlib import Path
import shutil
import tarfile

p = argparse.ArgumentParser()
p.add_argument('--archive', default='dataset/for_hackathon/for_hackathon')
p.add_argument('--output', default='dataset/extracted')
args = p.parse_args()
root = Path(args.output).resolve()
with tarfile.open(args.archive, 'r:') as archive:
    for bag in ('roundT_doubleT', 'doubleT_obstacle'):
        for filename in ('metadata.yaml', bag + '_0.db3'):
            member = archive.getmember('for_hackathon/' + bag + '/' + filename)
            if not member.isfile():
                raise ValueError('Expected regular file')
            target = root / bag / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise FileExistsError(target)
            with archive.extractfile(member) as source, target.open('xb') as dest:
                shutil.copyfileobj(source, dest, 8 * 1024 * 1024)
            print(target, member.size, flush=True)
