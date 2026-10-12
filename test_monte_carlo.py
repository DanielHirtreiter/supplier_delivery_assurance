import copy
import json
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).parent/'dist'))
from monte_carlo import validate,sample,evaluate,run
from mc_core import empirical_var_es

def config():
    c=json.loads((Path(__file__).parent/'dist/economic-example.json').read_text())
    c['n']=5000;c['common_probability']=0;c['common_days']=0
    c['suppliers']=c['suppliers'][:1]
    c['suppliers'][0].update(enabled=True,exposed_units=100,daily_demand=10,probability=1,
        delay_low=10,delay_mode=10,delay_high=10,buffer_days=2,price=200,margin=100,
        cancel_low=.25,cancel_mode=.25,cancel_high=.25,penalty=1,extra_cost_day=10,
        fixed_cost=0,premium_unit=0,saved_days=0,success=1,capacity_units=100,lead_days=0)
    return c

class MonteCarloTests(unittest.TestCase):
    def test_deterministic_accounting(self):
        c=config();r=run(c)
        # 80 affected units × 25% cancellation × €100 margin + 80×8×€1 + 8×€10.
        self.assertAlmostEqual(r['baseline']['mean']['mean'],2720)
        self.assertAlmostEqual(r['baseline']['var'],2720)
        self.assertAlmostEqual(r['baseline']['es'],2720)
        self.assertAlmostEqual(r['net_saving']['mean'],0)
        self.assertAlmostEqual(r['suppliers'][0]['mean_delayed_revenue'],12000)

    def test_no_event_no_cost(self):
        c=config();c['suppliers'][0]['probability']=0;c['suppliers'][0]['fixed_cost']=2000
        r=run(c);self.assertEqual(r['baseline']['mean']['mean'],0);self.assertEqual(r['mitigated']['mean']['mean'],0)
        self.assertGreater(r['baseline']['exceedance']['ci'][1],0)

    def test_no_exposure_and_full_stock_cover(self):
        for key,value in [('exposed_units',0),('buffer_days',84)]:
            c=config();c['suppliers'][0][key]=value
            r=run(c);self.assertEqual(r['baseline']['mean']['mean'],0);self.assertEqual(r['mitigated']['mean']['mean'],0)

    def test_capacity_lead_time_and_paid_failure(self):
        c=config();s=c['suppliers'][0];s.update(saved_days=8,capacity_units=20,lead_days=1)
        e=evaluate(c,sample(c,2000,np.random.default_rng(8)))
        self.assertTrue(np.allclose(e['recovered'],20))
        s.update(capacity_units=100,lead_days=9)
        e=evaluate(c,sample(c,2000,np.random.default_rng(8)))
        self.assertTrue(np.allclose(e['recovered'],10))
        s.update(success=0,fixed_cost=1000)
        r=run(c);self.assertAlmostEqual(r['net_saving']['mean'],-1000)

    def test_bernoulli_mean_benchmark(self):
        c=config();c['n']=50000;c['suppliers'][0]['probability']=.2
        r=run(c);expected=.2*2720;se=r['baseline']['mean']['mc_se']
        self.assertLess(abs(r['baseline']['mean']['mean']-expected),4*se)

    def test_atom_correct_expected_shortfall_and_book_aggregation(self):
        r=empirical_var_es(np.array([0]*99+[100]));self.assertEqual(r['var'],0);self.assertAlmostEqual(r['es'],20)
        r=empirical_var_es(np.array([a+b for a in range(1,6) for b in range(1,6)]))
        self.assertEqual(r['var'],9);self.assertAlmostEqual(r['es'],9.8)

    def test_shared_stress_and_tail_additivity(self):
        c=config();c['common_probability']=.3;c['common_days']=4
        b=copy.deepcopy(c['suppliers'][0]);b['id']='second';b['name']='Second independent exposure';c['suppliers'].append(b)
        r=run(c);self.assertAlmostEqual(r['diagnostics']['supplier_loss_correlation'][0][1],1)
        self.assertAlmostEqual(sum(s['tail_contribution'] for s in r['suppliers']),r['baseline']['es'])
        self.assertGreaterEqual(r['stress']['mean_loss'],r['baseline']['mean']['mean'])

    def test_reproducibility_and_real_example(self):
        c=json.loads((Path(__file__).parent/'dist/economic-example.json').read_text());c['n']=5000
        a=run(c);b=run(c);self.assertEqual(a,b);self.assertEqual(len(a['suppliers']),3)
        self.assertAlmostEqual(a['baseline']['mean']['mean'],sum(s['baseline']['mean']['mean'] for s in a['suppliers']))
        for s in a['suppliers']:
            self.assertAlmostEqual(s['baseline']['mean']['mean'],s['mean_lost_contribution']+s['mean_penalty']+s['mean_extra_cost'])
        self.assertGreaterEqual(a['assumption_stress'][0]['mean_loss'],a['baseline']['mean']['mean'])
        self.assertGreaterEqual(a['assumption_stress'][1]['mean_loss'],a['baseline']['mean']['mean'])
        self.assertLessEqual(a['assumption_stress'][2]['mean_loss'],a['baseline']['mean']['mean'])
        json.dumps(a,allow_nan=False)

    def test_validation_rejects_invalid_inputs(self):
        for key,value in [('n',1000000),('n',True),('threshold',float('nan')),('common_probability',1.2)]:
            c=config();c[key]=value
            with self.assertRaises(ValueError):validate(c)
        c=config();c['suppliers'][0]['delay_low']=20
        with self.assertRaises(ValueError):validate(c)
        c=config();c['suppliers'][0]['margin']=1000
        with self.assertRaises(ValueError):validate(c)

if __name__=='__main__':unittest.main()
