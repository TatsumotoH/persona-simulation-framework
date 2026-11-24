import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.patches as mpatches
import numpy as np

fig, ax = plt.subplots(1, 1, figsize=(16, 7))
ax.set_xlim(0, 20)
ax.set_ylim(0, 8)
ax.axis('off')

dark_gray = '#3A3A3A'
box_bg = '#F0F0F0'
border_gray = '#BBBBBB'
sub_bg = '#E8E8E8'

def draw_stage_box(ax, x, y, w, h, title, items, footer):
    outer = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.2",
                            facecolor='white', edgecolor=border_gray, linewidth=2)
    ax.add_patch(outer)
    ax.text(x + 0.4, y + h - 0.35, title,
            fontsize=18, fontweight='bold', ha='left', va='top', color=dark_gray)
    item_top = y + h - 1.6
    for i, item in enumerate(items):
        sub = FancyBboxPatch((x + 0.35, item_top - i * 1.25 - 0.05), w - 0.7, 0.9,
                              boxstyle="round,pad=0.1", facecolor=sub_bg, edgecolor='#CCCCCC', linewidth=1)
        ax.add_patch(sub)
        ax.text(x + w/2, item_top - i * 1.25 + 0.4, item,
                fontsize=13, ha='center', va='center', color=dark_gray)
    ax.text(x + w/2, y + 0.35, footer,
            fontsize=11, fontstyle='italic', ha='center', va='center', color='#777777')

# Stage 1
draw_stage_box(ax, 0.3, 0.8, 5.5, 6.5,
               'Stage 1: Diagnostic Battery',
               ['(1) Expression Test', '(2) Nomological Test', '(3) Belief-Update Test'],
               'Test multiple AI models\nfor persona validity')

# Pass/Fail Filter arrow + funnel
ax.annotate('', xy=(6.6, 4.0), xytext=(5.9, 4.0),
            arrowprops=dict(arrowstyle='->', color='#666666', lw=2))
funnel_x = [6.6, 7.2, 6.9, 6.6]
funnel_y = [4.7, 4.7, 3.7, 4.7]
ax.fill(funnel_x, funnel_y, color=dark_gray)
ax.text(6.9, 5.05, 'Pass/', fontsize=11, ha='center', va='center', color=dark_gray, fontweight='bold')
ax.text(6.9, 4.7, 'Fail', fontsize=11, ha='center', va='center', color=dark_gray, fontweight='bold')
ax.text(6.9, 3.35, 'Filter', fontsize=11, ha='center', va='center', color=dark_gray)
ax.annotate('', xy=(7.8, 4.0), xytext=(7.2, 4.0),
            arrowprops=dict(arrowstyle='->', color='#666666', lw=2))

# Stage 2
draw_stage_box(ax, 7.8, 0.8, 5.0, 6.5,
               'Stage 2: Calibration',
               ['Set target trait value', 'Overshoot → Step back', 'Verify at behavior level'],
               'Calibrated personas with\nverified behavioral differences')

# Verified checkmark arrow
ax.annotate('', xy=(13.5, 4.0), xytext=(12.9, 4.0),
            arrowprops=dict(arrowstyle='->', color='#666666', lw=2))
circle = plt.Circle((13.9, 4.0), 0.35, facecolor='#666666', edgecolor='#555555', linewidth=1.5)
ax.add_patch(circle)
ax.text(13.9, 4.0, '✓', fontsize=16, ha='center', va='center', color='white', fontweight='bold')
ax.text(13.9, 3.35, 'Verified', fontsize=11, ha='center', va='center', color=dark_gray)
ax.annotate('', xy=(14.8, 4.0), xytext=(14.3, 4.0),
            arrowprops=dict(arrowstyle='->', color='#666666', lw=2))

# Stage 3
draw_stage_box(ax, 14.8, 0.8, 5.0, 6.5,
               'Stage 3: Simulation',
               ['Set group composition', 'Run group deliberation', 'Measure group\ncomposition effects'],
               'Do calibrated personas\nproduce composition effects?')

plt.tight_layout()
import os
output_dir = os.path.join(os.path.dirname(__file__), '..', 'output')
os.makedirs(output_dir, exist_ok=True)
plt.savefig(os.path.join(output_dir, 'figure1_three_stage_framework.png'),
            dpi=300, bbox_inches='tight', facecolor='white', pad_inches=0.3)
print("Figure 1 saved successfully")
