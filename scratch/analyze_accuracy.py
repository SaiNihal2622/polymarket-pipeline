import json

with open(r'c:\Users\saini\Desktop\iplclaude\polymarket-pipeline\scratch\live_trades.json') as f:
    data = json.load(f)

print(f"Total trades: {len(data)}\n")
print(f"{'':2} {'ID':>4} {'Result':7} {'Side':4} {'Price':6} {'Conf':5} {'Edge':6} {'Category':12} {'Outcome':7} {'Question'}")
print("-" * 130)

wins = losses = pending = 0
for t in data:
    r = t.get('result', '?')
    if r == 'win': wins += 1; icon = 'WIN'
    elif r == 'loss': losses += 1; icon = 'LOSS'
    else: pending += 1; icon = 'PEND'
    
    q = t.get('market_question', '')[:65]
    side = t.get('side', '?')
    conf = t.get('confidence', 0)
    edge_val = t.get('edge', 0)
    price = t.get('entry_price', 0)
    cat = t.get('category', '?')
    outcome = t.get('outcome', '?')
    sig_type = t.get('signal_type', '?')
    
    print(f"  {t['id']:>4} {icon:7} {side:4} {price:>6.2f} {conf:>5.2f} {edge_val:>6.2f} {cat:12} {outcome:7} {q}")

resolved = wins + losses
acc = (wins / resolved * 100) if resolved else 0
print(f"\n=== SUMMARY ===")
print(f"Wins: {wins}, Losses: {losses}, Pending: {pending}")
print(f"Resolved: {resolved}, Accuracy: {acc:.1f}%")

# Analyze loss patterns
print(f"\n=== LOSS ANALYSIS ===")
for t in data:
    if t.get('result') == 'loss':
        q = t.get('market_question', '')[:80]
        side = t.get('side', '?')
        cat = t.get('category', '?')
        conf = t.get('confidence', 0)
        sig_type = t.get('signal_type', '?')
        outcome = t.get('outcome', '?')
        print(f"  Side={side} Cat={cat} Conf={conf} SigType={sig_type} Outcome={outcome}")
        print(f"    Q: {q}")

# Win analysis
print(f"\n=== WIN ANALYSIS ===")
for t in data:
    if t.get('result') == 'win':
        q = t.get('market_question', '')[:80]
        side = t.get('side', '?')
        cat = t.get('category', '?')
        conf = t.get('confidence', 0)
        sig_type = t.get('signal_type', '?')
        outcome = t.get('outcome', '?')
        print(f"  Side={side} Cat={cat} Conf={conf} SigType={sig_type} Outcome={outcome}")
        print(f"    Q: {q}")

# Category breakdown
print(f"\n=== BY CATEGORY ===")
cats = {}
for t in data:
    cat = t.get('category', 'unknown')
    if cat not in cats:
        cats[cat] = {'wins': 0, 'losses': 0, 'pending': 0}
    r = t.get('result', 'pending')
    if r == 'win': cats[cat]['wins'] += 1
    elif r == 'loss': cats[cat]['losses'] += 1
    else: cats[cat]['pending'] += 1

for cat, stats in sorted(cats.items()):
    resolved = stats['wins'] + stats['losses']
    acc = (stats['wins'] / resolved * 100) if resolved else 0
    print(f"  {cat:15} {stats['wins']}W/{stats['losses']}L/{stats['pending']}P  Acc: {acc:.0f}%")

# Side breakdown
print(f"\n=== BY SIDE ===")
sides = {}
for t in data:
    side = t.get('side', '?')
    if side not in sides:
        sides[side] = {'wins': 0, 'losses': 0}
    r = t.get('result', 'pending')
    if r == 'win': sides[side]['wins'] += 1
    elif r == 'loss': sides[side]['losses'] += 1

for side, stats in sides.items():
    resolved = stats['wins'] + stats['losses']
    acc = (stats['wins'] / resolved * 100) if resolved else 0
    print(f"  {side:5} {stats['wins']}W/{stats['losses']}L  Acc: {acc:.0f}%")