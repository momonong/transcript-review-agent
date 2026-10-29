import unittest
from transcript_review_agent.__main__ import make_runner,parser
from transcript_review_agent.core import ReviewInputError


class CliConfigurationTests(unittest.TestCase):
    def test_default_demo_does_not_require_a_model(self):
        args=parser().parse_args(['serve'])
        runner,kind=make_runner(args,optional=True)
        self.assertIsNone(runner);self.assertEqual(kind,'fixed_baseline')

    def test_configured_models_are_lazy_until_runner_is_called(self):
        args=parser().parse_args(['serve','--whisper-model','missing-whisper','--agent-model','missing-phi'])
        runner,kind=make_runner(args,optional=True)
        self.assertTrue(callable(runner));self.assertEqual(kind,'llm_agent')

    def test_policy_model_must_match_explicit_policy(self):
        args=parser().parse_args(['serve','--fixture','fixture.json','--policy','agent'])
        with self.assertRaises(ReviewInputError):make_runner(args,optional=True)
        args=parser().parse_args(['serve','--fixture','fixture.json','--policy','fixed','--agent-model','phi'])
        with self.assertRaises(ReviewInputError):make_runner(args,optional=True)


if __name__=='__main__':unittest.main()
