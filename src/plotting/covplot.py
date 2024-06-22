#!/usr/bin/env python3
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import os
import sys
import numpy as np

plt.style.use('seaborn-v0_8-paper')
sns.set_style("whitegrid")
plt.rcParams.update({'font.size': 24})

def main(csvs):
    df = pd.DataFrame()
    csvs.sort()

    for filename in csvs:
        tmp_filename = os.path.basename(filename)
        name, ext = tmp_filename.split('.')
        idx, method, target = name.split("-")
        target = target.replace("_", " ")
        method = method.replace("=", "-")
        data = pd.read_csv(filename)
        data['method'] = method
        data['target'] = target
        df = pd.concat([df, data], ignore_index=True)

    data = None
    methods = df['method'].unique()
    targets = df['target'].unique()

    # https://matplotlib.org/stable/_images/sphx_glr_colormaps_020.png
    offset = 0
    palette_i = sns.color_palette(n_colors=5)
    palette = list(map(lambda x: plt.cm.tab20(x[0]), palette_i))
    palette_bg = list(map(lambda x: plt.cm.tab20(x[1]), palette_i))

    # Create subplots for the diagrams
    fig, axes = plt.subplots(2, 4, figsize=(20, 10), sharey=True)

    for i, target in enumerate(targets[:4]):
        ax = axes[0, i]
        ax.set_title(target.upper())

        data = df[(df['target'] == target) & (df['method'] == "noifacenommio")]
        ax.fill_between(data['time'], y1=data['min'], y2=data['max'], color=palette[0], alpha=0.3)
        ax.plot(data['time'], data['avg'], label=method, linestyle='--', linewidth=2, alpha=1, color=palette[0])
        data = df[(df['target'] == target) & (df['method'] == "ifacenommio")]
        ax.fill_between(data['time'], y1=data['min'], y2=data['max'], color=palette[1], alpha=0.3)
        ax.plot(data['time'], data['avg'], label=method, linestyle='--', linewidth=2, alpha=1, color=palette[1])
        data = df[(df['target'] == target) & (df['method'] == "noifacemmio")]
        ax.fill_between(data['time'], y1=data['min'], y2=data['max'], color=palette[4], alpha=0.3)
        ax.plot(data['time'], data['avg'], label=method, linestyle='--', linewidth=2, alpha=1, color=palette[4])
        data = df[(df['target'] == target) & (df['method'] == "ifacemmio")]
        ax.fill_between(data['time'], y1=data['min'], y2=data['max'], color=palette[3], alpha=0.3)
        ax.plot(data['time'], data['avg'], label=method, linestyle='--', linewidth=2, alpha=1, color=palette[3])

        ax.patch.set_edgecolor('black')
        ax.patch.set_linewidth('1')
        ax.set_ylabel('Edge Coverage', weight='bold')
        ax.set_xlabel('Time (hh:mm)', weight='bold')
        ax.set_xticks([0, 21600, 43200, 64800, 86400])
        ax.set_xticklabels(['00:00', '6:00', '12:00', '18:00', '24:00'])
    for i, target in enumerate(targets[4:]):
        ax = axes[1, i]
        ax.set_title(target.upper())

        data = df[(df['target'] == target) & (df['method'] == "noifacenommio")]
        ax.fill_between(data['time'], y1=data['min'], y2=data['max'], color=palette[0], alpha=0.3)
        ax.plot(data['time'], data['avg'], label=method, linestyle='--', linewidth=2, alpha=1, color=palette[0])
        data = df[(df['target'] == target) & (df['method'] == "ifacenommio")]
        ax.fill_between(data['time'], y1=data['min'], y2=data['max'], color=palette[1], alpha=0.3)
        ax.plot(data['time'], data['avg'], label=method, linestyle='--', linewidth=2, alpha=1, color=palette[1])
        data = df[(df['target'] == target) & (df['method'] == "noifacemmio")]
        ax.fill_between(data['time'], y1=data['min'], y2=data['max'], color=palette[4], alpha=0.3)
        ax.plot(data['time'], data['avg'], label=method, linestyle='--', linewidth=2, alpha=1, color=palette[4])
        data = df[(df['target'] == target) & (df['method'] == "ifacemmio")]
        ax.fill_between(data['time'], y1=data['min'], y2=data['max'], color=palette[3], alpha=0.3)
        ax.plot(data['time'], data['avg'], label=method, linestyle='--', linewidth=2, alpha=1, color=palette[3])

        ax.patch.set_edgecolor('black')
        ax.patch.set_linewidth('1')
        ax.set_ylabel('Edge Coverage', weight='bold')
        ax.set_xlabel('Time (hh:mm)', weight='bold')
        ax.set_xticks([0, 21600, 43200, 64800, 86400])
        ax.set_xticklabels(['00:00', '6:00', '12:00', '18:00', '24:00'])

    axes[1, 3].axis('off')

    ls = ['iface⁻  + mmio⁻', 'iface⁺  + mmio⁻', 'iface⁻  + mmio⁺', 'iface⁺  + mmio⁺']

    data = df[(df['target'] == target[0]) & (df['method'] == "noifacenommio")]
    axes[1, 3].plot(data['time'], data['avg'], c=palette[0], alpha=0, label=ls[0])
    data = df[(df['target'] == target[0]) & (df['method'] == "ifacenommio")]
    axes[1, 3].plot(data['time'], data['avg'], c=palette[1], alpha=0, label=ls[1])
    data = df[(df['target'] == target[0]) & (df['method'] == "noifacemmio")]
    axes[1, 3].plot(data['time'], data['avg'], c=palette[4], alpha=0, label=ls[2])
    data = df[(df['target'] == target[0]) & (df['method'] == "ifacemmio")]
    axes[1, 3].plot(data['time'], data['avg'], c=palette[3], alpha=0, label=ls[3])

    leg = axes[1, 3].legend(loc='center', frameon=False, fontsize='x-small')
    for lh in leg.legend_handles:
        lh.set_alpha(1)

    # Save the plot to a PDF file
    plt.tight_layout()
    plt.savefig('plot.pdf', bbox_inches='tight')

if __name__=="__main__":
    main(sys.argv[1:])
