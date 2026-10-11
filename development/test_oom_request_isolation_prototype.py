import unittest

from oom_request_isolation_prototype import IsolationProof, OomDisposition, classify_cuda_oom


class OomIsolationDecisionTests(unittest.TestCase):
    def test_missing_proof_restarts_single_request_worker(self):
        self.assertEqual(
            classify_cuda_oom(batch_size=1, proof=None),
            OomDisposition.REQUEST_ERROR_RESTART_WORKER,
        )

    def test_shared_batch_never_continues(self):
        proof = IsolationProof(True, True, True, True, True)
        self.assertEqual(
            classify_cuda_oom(batch_size=2, proof=proof),
            OomDisposition.BATCH_ERROR_RESTART_WORKER,
        )

    def test_incomplete_transaction_proof_restarts(self):
        proof = IsolationProof(True, True, True, False, True)
        self.assertEqual(
            classify_cuda_oom(batch_size=1, proof=proof),
            OomDisposition.REQUEST_ERROR_RESTART_WORKER,
        )

    def test_only_complete_isolation_proof_allows_continue(self):
        proof = IsolationProof(True, True, True, True, True)
        self.assertEqual(
            classify_cuda_oom(batch_size=1, proof=proof),
            OomDisposition.REQUEST_ERROR_SAFE_CONTINUE,
        )


if __name__ == "__main__":
    unittest.main()
