"""Render the saved development experiment; never alter detector results."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import numpy as np


def render(directory):
    data = json.loads((directory / 'visual_replay.json').read_text(encoding='utf-8'))
    rows = data['frames']
    frame_label = ', '.join(str(row['index']) for row in rows)
    fig, axes = plt.subplots(2, 3, figsize=(15, 10), constrained_layout=True)
    for ax, index in zip(axes[0], (rows[0]['index'], rows[len(rows)//2]['index'], rows[-1]['index'])):
        row = next(r for r in rows if r['index'] == index)
        points = np.fromfile(directory / f'frame_{index:05d}.xyzf', dtype='<f4').reshape(-1, 3)
        ax.hist2d(points[:, 0], -points[:, 1], bins=(220, 300), range=((-4, 4), (0, 45)),
                  cmap='Greys', norm=LogNorm())
        rails = np.asarray(row['auto']['rails'])
        if len(rails):
            for left, right in ((0, 2), (1, 3)):
                ax.plot(rails[[left, right], 0], -rails[[left, right], 1], color='#008952', lw=2)
            e = row['live']['envelope']
            axis = e['axis']
            center = np.array([axis['a'], axis['b']])
            n = np.array([axis['nx'], axis['ny'], 0])
            for lateral in (e['core']['left'], e['core']['right']):
                boundary = center + n * lateral
                ax.plot(boundary[:, 0], -boundary[:, 1], color='#d97800', lw=1.8, ls='--')
            ax.plot(center[:, 0], -center[:, 1], color='#2475cb', lw=1)
        ax.set(title=f"Frame {index} / bag +{row['bag_offset_seconds']:.2f} s",
               xlabel='Source X (m, assumed)', ylabel='Forward -Y (m, assumed)', xlim=(-4, 4), ylim=(0, 45))
    time = np.array([r['bag_offset_seconds'] for r in rows])
    near = [r['auto'].get('diagnostics', {}).get('forwardRange', [np.nan, np.nan])[0] for r in rows]
    far = [r['auto'].get('diagnostics', {}).get('forwardRange', [np.nan, np.nan])[1] for r in rows]
    axes[1, 0].plot(time, near, label='Supported start', color='#008952')
    axes[1, 0].plot(time, far, label='Supported end', color='#2475cb')
    axes[1, 0].set(title='Measured rail-hypothesis interval', ylabel='Forward -Y (m, assumed)')
    axes[1, 0].legend()
    axes[1, 1].plot(time, [r['live']['counts']['core'] if r['auto']['status']=='AUTO_HYPOTHESIS' else np.nan for r in rows], color='#c13841')
    axes[1, 1].set(title='Core returns: candidates, not obstacles', ylabel='Number of returns')
    axes[1, 2].plot(time, [r['processing_ms'] for r in rows], color='#7554af')
    axes[1, 2].set(title='Local Node: auto rails + envelope', ylabel='Milliseconds (no I/O or UI)')
    for ax in axes[1]:
        ax.set_xlabel('Bag offset (s)')
        ax.grid(alpha=.2)
        for r in rows:
            if r['auto']['status'] != 'AUTO_HYPOTHESIS':
                ax.axvline(r['bag_offset_seconds'], color='#777777', ls=':', lw=1.3)
    fig.suptitle(f'new_data: frame-local transfer, saved frames {frame_label}\n'
                 'Green: rail hypothesis | Orange: reference width | Blue: local axis\n'
                 'UNKNOWN outside supported segment; no deskew, no clearance decision', fontsize=13)
    fig.savefig(directory / 'transfer_overview.png', dpi=140)
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    render(parser.parse_args().directory)
