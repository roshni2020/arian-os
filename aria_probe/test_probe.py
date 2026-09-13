import copy
import unittest
from probe import validate

class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.p={'observation':'Observed baseline errors','hypothesis':'Add features','reason':'Missing signal',
            'experiment':{'model':'logistic_regression','feature_count':4,'C':1,'class_weight':None},
            'previous_decision':{'decision':'KEEP','reason':'Baseline reference','learning':'Two features omit signal'}}

    def test_valid(self):
        self.assertEqual(validate(self.p,[])['feature_count'],4)

    def test_untrusted_config(self):
        for key,value in [('shell','echo unsafe'),('model','arbitrary_code'),('feature_count',True),('C',float('nan')),('C',1000)]:
            p=copy.deepcopy(self.p)
            p['experiment'][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                validate(p,[])

    def test_duplicate(self):
        with self.assertRaises(ValueError):
            validate(self.p,[{'experiment':validate(self.p,[])}])

    def test_missing_decision(self):
        self.p['previous_decision']={}
        with self.assertRaises(ValueError):
            validate(self.p,[])

if __name__=='__main__': unittest.main()
