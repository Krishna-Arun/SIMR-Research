import json
d = json.load(open('golden_samples.json'))
for g in d['samples']:
    print('='*92)
    print('%s [%s]  %s vs %s' % (g['pair_id'], g['tag'], g['intervention_a'], g['intervention_b']))
    print('  match score=%s comorbid_dist=%s | HPI leak A=%s' % (
        g['match_quality']['score'], g['match_quality']['comorbidity_distance'], g['hpi_leak_a']))
    for m in g['scored_markers']:
        gtA = g['ground_truth'][m]['A']; gtB = g['ground_truth'][m]['B']
        if not gtA or not gtB: continue
        truth = '<' if gtA['post_final'] < gtB['post_final'] else '>'
        print('  --- %s ---' % m)
        print('      GT:  A %s->%s (%s)   B %s->%s (%s)   [truth: A_final %s B_final]' % (
            gtA['baseline'], gtA['post_final'], gtA['direction'],
            gtB['baseline'], gtB['post_final'], gtB['direction'], truth))
        for name, md in g['models'].items():
            mm = md.get(m)
            if not mm or not mm['A'] or not mm['B']:
                print('      %-28s (missing)' % name); continue
            A, B = mm['A'], mm['B']
            flags = []
            if mm['dir_conf_disagree_A']: flags.append('DIR!=CONF')
            if mm['scale_off_A']: flags.append('SCALE-OFF')
            print('      %-28s A %s->%s (%s/conf:%s)  B %s->%s (%s)  MCCS=%s %s' % (
                name, A['start'], A['final'], A['parsed_dir'], A['conf_dir'],
                B['start'], B['final'], B['parsed_dir'],
                'OK' if mm['mccs_correct'] else 'X', ' '.join(flags)))
