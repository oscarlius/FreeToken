# R067e batch 165 independent pre-GPU classification

The immutable launch receipt records candidate `b86190d78be3b1b4b55f989c98ce963630e425dd`, while the child wrapper invoked `d07.require_child_receipt()` before assigning the retry plan’s candidate to the D07 module. D07 compares the receipt’s candidate against its default candidate at `d07_g3g4_prepare.py:208`; the raw batch log therefore ends with `D07 child launch receipt binding differs` from `retry2_runner.py:171`.

This failure occurs before `parent.child()`, Effects construction, D07 lock acquisition, materialization, a service start, or a generation request. Batch 165 is a pre-GPU wrapper/harness failure, not a product `not_met`; the launch receipt and batch log must remain unchanged.

Lesson: the earlier nine-pass CPU suite exercised controller and a fake lifecycle, but it did not exercise the actual child process’s module-global D07 receipt contract. Future CPU admission evidence must use a real child process birth-bound receipt and include both a matching-plan positive case and a mismatched-candidate negative case.
