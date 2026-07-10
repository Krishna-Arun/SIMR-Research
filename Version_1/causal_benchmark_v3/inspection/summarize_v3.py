import json
d = json.load(open('golden_v3.json'))
for g in d['samples']:
    print('='*100)
    print('%s [%s]  %s vs %s' % (g['pair_id'], g['tag'], g['arm_a'], g['arm_b']))
    for m, md in g['per_marker'].items():
        gt = md['gt']
        print('  --- %s (%s) ---  GT benefit: %s (DiD=%s) | A %s->%s  B %s->%s' % (
            m, md['role'], (gt['benefit_label'] or '?').upper(), gt['did'],
            gt['baseline_a'], gt['final_a'], gt['baseline_b'], gt['final_b']))
        for name, mm in md['models'].items():
            A = mm['A']
            if not A:
                print('      %-26s (missing)' % name); continue
            probs = A['logit_probs']
            pstr = ('P[r=%.2f f=%.2f s=%.2f]' % (probs['rising'],probs['falling'],probs['stable'])) if probs else 'P[none]'
            flags=[]
            if mm['benefit_correct'] is True: flags.append('BENEFIT OK')
            elif mm['benefit_correct'] is False: flags.append('BENEFIT X')
            if mm['parse_ne_logit']: flags.append('parse!=logit')
            if mm['scale_off']: flags.append('SCALE-OFF')
            if mm['garbage']: flags.append('GARBAGE')
            print('      %-26s pred=%-12s parsed=%-8s argmax=%-8s %s  %s' % (
                name, (mm['pred_benefit'] or '?'), str(A['parsed_dir']), str(A['logit_argmax']), pstr, ' '.join(flags)))
