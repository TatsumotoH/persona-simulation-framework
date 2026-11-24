import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch

fig, ax = plt.subplots(1, 1, figsize=(13, 10))
ax.set_xlim(0, 14)
ax.set_ylim(0, 11)
ax.axis('off')

# Colors
bg_gray = '#F5F5F5'
dark_gray = '#4A4A4A'
border_gray = '#CCCCCC'
pass_color = '#2D2D2D'
fail_color = '#999999'
red_accent = '#CC3333'

def draw_test_box(ax, x, y, w, h, title, subtitle, content_lines, pass_text, fail_text, num):
    # Main box
    box = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.15", 
                          facecolor=bg_gray, edgecolor=border_gray, linewidth=1.5)
    ax.add_patch(box)
    
    # Test number and title
    ax.text(x + w/2, y + h - 0.35, f'({num}) {title}', 
            fontsize=20, fontweight='bold', ha='center', va='top', color=dark_gray)
    
    # Subtitle
    ax.text(x + w/2, y + h - 0.75, subtitle, 
            fontsize=14, fontstyle='italic', ha='center', va='top', color='#666666')
    
    # Content lines
    for i, line in enumerate(content_lines):
        ax.text(x + w/2, y + h - 1.2 - i*0.35, line, 
                fontsize=14, ha='center', va='top', color=dark_gray)
    
    # Pass text (right side)
    pass_y = y + h/2 + 0.3
    ax.text(x + w + 0.4, pass_y, 'PASS:', fontsize=13, fontweight='bold', 
            ha='left', va='center', color=pass_color)
    ax.text(x + w + 0.4, pass_y - 0.35, pass_text, fontsize=13, 
            ha='left', va='center', color=pass_color)
    
    # Fail text (right side)
    ax.text(x + w + 0.4, pass_y - 0.9, f'FAIL: {fail_text}', fontsize=13, 
            ha='left', va='center', color=fail_color, fontstyle='italic')

# Left label: Business Case + Persona Assignment
left_box = FancyBboxPatch((0.3, 4.2), 1.8, 2.5, boxstyle="round,pad=0.1",
                           facecolor='white', edgecolor=dark_gray, linewidth=1.5)
ax.add_patch(left_box)
ax.text(1.2, 5.9, 'Business Case', fontsize=16, fontweight='bold', ha='center', va='center', color=dark_gray)
ax.text(1.2, 5.45, '+ Persona', fontsize=16, fontweight='bold', ha='center', va='center', color=dark_gray)
ax.text(1.2, 5.0, 'Assignment', fontsize=16, fontweight='bold', ha='center', va='center', color=dark_gray)

# Arrows from left box to each test
for ty in [8.7, 5.45, 2.0]:
    ax.annotate('', xy=(2.8, ty), xytext=(2.1, 5.45),
                arrowprops=dict(arrowstyle='->', color='#888888', lw=1.5))

# ---- Test 1: Expression ----
box1 = FancyBboxPatch((2.8, 7.6), 6.2, 2.5, boxstyle="round,pad=0.15",
                       facecolor=bg_gray, edgecolor=border_gray, linewidth=1.5)
ax.add_patch(box1)

ax.text(5.9, 9.75, '(1) Persona Expression Test', 
        fontsize=20, fontweight='bold', ha='center', va='top', color=dark_gray)
ax.text(5.9, 9.35, 'Persona spec → Does it shape judgment?', 
        fontsize=14, fontstyle='italic', ha='center', va='top', color='#666666')

# Sub-boxes for Role Divergence and Rote Response
sub1a = FancyBboxPatch((3.2, 7.85), 2.6, 1.2, boxstyle="round,pad=0.1",
                        facecolor='white', edgecolor='#AAAAAA', linewidth=1)
ax.add_patch(sub1a)
ax.text(4.5, 8.85, 'Role Divergence', fontsize=15, fontweight='bold', ha='center', va='center', color=dark_gray)
ax.text(4.5, 8.45, 'Same facts', fontsize=13, ha='center', va='center', color='#666666')
ax.text(4.5, 8.15, '→ Different categories?', fontsize=13, ha='center', va='center', color='#666666')

sub1b = FancyBboxPatch((6.2, 7.85), 2.4, 1.2, boxstyle="round,pad=0.1",
                        facecolor='white', edgecolor='#AAAAAA', linewidth=1)
ax.add_patch(sub1b)
ax.text(7.4, 8.85, 'Rote Response', fontsize=15, fontweight='bold', ha='center', va='center', color=dark_gray)
ax.text(7.4, 8.45, 'Strategy ranking', fontsize=13, ha='center', va='center', color='#666666')
ax.text(7.4, 8.15, '→ Not textbook order?', fontsize=13, ha='center', va='center', color='#666666')

# Pass/Fail for Test 1
ax.text(9.4, 9.2, 'PASS: Judgments differ', fontsize=14, fontweight='bold',
        ha='left', va='center', color=pass_color)
ax.text(9.4, 8.8, 'by persona', fontsize=14, fontweight='bold',
        ha='left', va='center', color=pass_color)
ax.text(9.4, 8.2, 'FAIL: Identical (silent failure)', fontsize=13,
        ha='left', va='center', color=fail_color, fontstyle='italic')

# ---- Test 2: Nomological ----
box2 = FancyBboxPatch((2.8, 4.2), 6.2, 2.5, boxstyle="round,pad=0.15",
                       facecolor=bg_gray, edgecolor=border_gray, linewidth=1.5)
ax.add_patch(box2)

ax.text(5.9, 6.35, '(2) Persona Nomological Test',
        fontsize=20, fontweight='bold', ha='center', va='top', color=dark_gray)
ax.text(5.9, 5.95, 'Attribute X → Does Behavior Y follow theory?',
        fontsize=14, fontstyle='italic', ha='center', va='top', color='#666666')

# Sub-boxes for Self-Report and Behavioral
sub2a = FancyBboxPatch((3.2, 4.45), 2.6, 1.2, boxstyle="round,pad=0.1",
                        facecolor='white', edgecolor='#AAAAAA', linewidth=1)
ax.add_patch(sub2a)
ax.text(4.5, 5.45, 'Self-Report', fontsize=15, fontweight='bold', ha='center', va='center', color=dark_gray)
ax.text(4.5, 5.05, 'Scale scores move', fontsize=13, ha='center', va='center', color='#666666')
ax.text(4.5, 4.75, '(all models pass)', fontsize=13, ha='center', va='center', color='#666666')

sub2b = FancyBboxPatch((6.2, 4.45), 2.4, 1.2, boxstyle="round,pad=0.1",
                        facecolor='white', edgecolor='#AAAAAA', linewidth=1)
ax.add_patch(sub2b)
ax.text(7.4, 5.45, 'Behavioral', fontsize=15, fontweight='bold', ha='center', va='center', color=dark_gray)
ax.text(7.4, 5.05, 'But does behavior', fontsize=13, ha='center', va='center', color=dark_gray, fontweight='bold')
ax.text(7.4, 4.75, 'actually change?', fontsize=13, ha='center', va='center', color=dark_gray, fontweight='bold')

# Pass/Fail for Test 2
ax.text(9.4, 5.8, 'PASS: Trait → Behavior', fontsize=14, fontweight='bold',
        ha='left', va='center', color=pass_color)
ax.text(9.4, 5.4, 'as theory predicts', fontsize=14, fontweight='bold',
        ha='left', va='center', color=pass_color)
ax.text(9.4, 4.8, 'FAIL: Scale moves,', fontsize=13,
        ha='left', va='center', color=fail_color, fontstyle='italic')
ax.text(9.4, 4.5, 'behavior doesn\'t', fontsize=13,
        ha='left', va='center', color=fail_color, fontstyle='italic')

# ---- Test 3: Belief Update ----
box3 = FancyBboxPatch((2.8, 0.7), 6.2, 2.5, boxstyle="round,pad=0.15",
                       facecolor=bg_gray, edgecolor=border_gray, linewidth=1.5)
ax.add_patch(box3)

ax.text(5.9, 2.85, '(3) Persona Belief-Update Test',
        fontsize=20, fontweight='bold', ha='center', va='top', color=dark_gray)
ax.text(5.9, 2.45, 'Argument quality → Position maintain / revise?',
        fontsize=14, fontstyle='italic', ha='center', va='top', color='#666666')

# Sub-box: Evidence Based
sub3a = FancyBboxPatch((3.2, 0.95), 2.6, 1.2, boxstyle="round,pad=0.1",
                        facecolor='white', edgecolor='#AAAAAA', linewidth=1)
ax.add_patch(sub3a)
ax.text(4.5, 1.95, 'Evidence Based', fontsize=15, fontweight='bold', ha='center', va='center', color=dark_gray)
ax.text(4.5, 1.55, 'Strong → Should change', fontsize=13, ha='center', va='center', color='#666666')
ax.text(4.5, 1.25, 'Weak → Should resist', fontsize=13, ha='center', va='center', color='#666666')

# Sub-box: Majority Based
sub3b = FancyBboxPatch((6.2, 0.95), 2.4, 1.2, boxstyle="round,pad=0.1",
                        facecolor='white', edgecolor='#AAAAAA', linewidth=1)
ax.add_patch(sub3b)
ax.text(7.4, 1.95, 'Majority Based', fontsize=15, fontweight='bold', ha='center', va='center', color=dark_gray)
ax.text(7.4, 1.55, 'Majority pressure', fontsize=13, ha='center', va='center', color='#666666')
ax.text(7.4, 1.25, '→ Should resist', fontsize=13, ha='center', va='center', color='#666666')

# Pass/Fail for Test 3
ax.text(9.4, 2.3, 'PASS: Responds to', fontsize=14, fontweight='bold',
        ha='left', va='center', color=pass_color)
ax.text(9.4, 1.9, 'strong arguments,', fontsize=14, fontweight='bold',
        ha='left', va='center', color=pass_color)
ax.text(9.4, 1.5, 'resists pressure', fontsize=14, fontweight='bold',
        ha='left', va='center', color=pass_color)
ax.text(9.4, 0.9, 'FAIL: Rigid / Acquiescent', fontsize=13,
        ha='left', va='center', color=fail_color, fontstyle='italic')

# Bottom note
ax.text(5.9, 0.15, 'All three tests must be passed for valid group deliberation simulation',
        fontsize=14, ha='center', va='center', color=dark_gray,
        bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor=border_gray, linewidth=1))

plt.tight_layout()
import os
output_dir = os.path.join(os.path.dirname(__file__), '..', 'output')
os.makedirs(output_dir, exist_ok=True)
plt.savefig(os.path.join(output_dir, 'figure3_diagnostic_battery.png'),
            dpi=300, bbox_inches='tight', facecolor='white', pad_inches=0.3)
print("Figure saved successfully")
